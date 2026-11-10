"""Hosted composition of shared RAG over an authorized PostgreSQL snapshot."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import importlib.util

from sqlalchemy import select

from osii.domain.library import Library
from osii.model_provider import ProviderError
from osii.persistence.postgres import datasets
from osii.rag.strategies import Decision, Evidence, Question, Scope, StrategyError
from osii.rag.strategies.decisions import decision_messages, decision_response_format, parse_decision
from osii.rag.strategies.experiments import run_profile
from osii.rag.strategies.http_reranker import create_reranker
from osii.rag.strategies.profiles import PROFILES, Profile
from osii.rag.strategies.tracing import AgentTrace
from osii.search.engine import tokens
from osii.server.model_connections import ConfiguredModelProvider


SERVER_PROFILES = (*PROFILES, Profile("coarse-iterative-v1", "Coarse full-text + iterative",
    "Find documents with matching terms, then search passages and follow up within the authorized scope.",
    "hybrid", strategy="iterative", rounds=3))
STOP_WORDS = set("a an and are as at be by did do does for from how in is it of on or that the their this to was were what when where which who why with".split())


class CorpusChanged(StrategyError):
    pass


def profiles(store, connections, account) -> dict:
    model = store.configuration().get("chat_model", "")
    ranker = create_reranker(connections.endpoints()["rerank"])
    items = []
    for profile in SERVER_PROFILES:
        reason = None
        if importlib.util.find_spec("haystack") is None:
            reason = "This deployment needs the rag-haystack dependency."
        elif profile.rerank and ranker is None:
            reason = "Configure a reranker in administrator Model settings."
        elif profile.strategy == "iterative" and not model:
            reason = "Select a chat model in administrator Model settings."
        items.append({**asdict(profile), "coarse_fulltext": profile.id == "coarse-iterative-v1",
                      "available": reason is None, "unavailable_reason": reason})
    return {"profiles": items, "chat_model": model or "extractive", "provider": "openai" if model else "extractive",
            "can_inspect_trace": account["role"] == "admin"}


class RagSession:
    """Comparisons share one materialized corpus, scope, history, and model config.

    No database transaction is held during model calls. Guards reject a run if
    current corpus/config/collection membership changes while it executes.
    """
    def __init__(self, store, provider, connections, account, query, scope, history):
        self.store, self.connections, self.account = store, connections, account
        kind = scope.get("scope_type", "root")
        if not isinstance(kind, str) or kind not in {"root", "object", "folder", "collection"}:
            raise StrategyError("Unsupported scope")
        key = {"object": "file_id", "folder": "folder_id", "collection": "collection_id"}.get(kind, "")
        scope_id = scope.get(key) or ""
        if not isinstance(scope_id, str):
            raise StrategyError("Scope identifier must be text")
        self.question = Question(query, Scope(kind, scope_id),
                                 tuple((turn.get("role"), turn.get("content", "")) for turn in history))
        self.scope = self.question.scope.payload()
        self.provider = connections.provider() if isinstance(provider, ConfiguredModelProvider) else provider
        self.revision, self.documents, self.rows = Library(store, self.provider).scoped(self.scope, account["id"])
        self.configuration = deepcopy(store.configuration())
        self.endpoints = connections.endpoints()
        self.collection = self._collection()
        self.model = self.configuration.get("chat_model", "")
        self.embedding_model = self.configuration.get("embedding_model", "")
        self.reranker = create_reranker(self.endpoints["rerank"])
        self.available = {p["id"]: p for p in profiles(store, connections, account)["profiles"]}
        self.retrieval = Library(store, self.provider).retrieval
        self.guard()

    def _collection(self):
        if self.scope["scope_type"] != "collection":
            return None
        return next((c for c in self.store.collection_records(self.account["id"])
                     if c["id"] == self.scope["collection_id"]), None)

    def guard(self):
        with self.store.engine.connect() as connection:
            revision = connection.execute(select(datasets.c.revision).where(datasets.c.id == "shared")).scalar() or 0
        if (revision != self.revision or self.store.configuration() != self.configuration
                or self.connections.endpoints() != self.endpoints or self._collection() != self.collection):
            raise CorpusChanged("The corpus, scope membership, or model configuration changed. Start a new run.")

    def validate(self, identifiers):
        for identifier in identifiers:
            capability = self.available.get(identifier)
            if capability is None:
                raise StrategyError("Unknown RAG profile")
            if not capability["available"]:
                raise StrategyError(capability["unavailable_reason"])

    def run(self, identifier: str) -> dict:
        self.validate([identifier])
        profile = next(p for p in SERVER_PROFILES if p.id == identifier)
        trace = AgentTrace(profile.id)
        row_map, calls, warnings, modes = {}, [], [], []
        document_map = {doc["file_id"]: doc for doc in self.documents}
        result = None
        error = None

        def retrieve(query, *, top_k):
            self.guard()
            with trace.span("retrieval", "Search authorized evidence", query=query, input_count=len(self.rows),
                            candidate_limit=top_k) as search_stage:
                rows = self.rows
                if identifier == "coarse-iterative-v1":
                    terms = sorted(set(tokens(query)) - STOP_WORDS)
                    with trace.span("coarse_fulltext", "Coarse full-text document search", query=query,
                                    terms=terms, matching="normalized token OR", input_count=len(self.documents)) as stage:
                        if not terms:
                            raise StrategyError("The coarse search needs a more specific query")
                        matched = [doc for doc in self.documents if set(terms) & set(tokens(doc["text"]))]
                        stage.items = [{"id": doc["file_id"], "file_id": doc["file_id"],
                                        "source_relpath": doc["source_relpath"]} for doc in matched]
                        stage.outputs.update(output_count=len(matched), exact_count=True, limit_reached=len(matched) > 500)
                        if len(matched) > 500:
                            raise StrategyError("Coarse search matched over 500 documents; refine the question or scope")
                        allowed = {doc["file_id"] for doc in matched}
                        stage.excluded = [{"id": doc["file_id"], "file_id": doc["file_id"],
                                           "source_relpath": doc["source_relpath"], "reason": "no matching full-text term"}
                                          for doc in self.documents if doc["file_id"] not in allowed]
                        rows = [row for row in rows if row["file_id"] in allowed]
                vector = None
                if profile.retrieval != "lexical" and self.embedding_model and any(row.get("embedding_model") == self.embedding_model for row in rows):
                    if (not self.store.login_allowed("search:" + self.account["id"], failed=True, maximum=20)
                            or not self.store.login_allowed("search:global", failed=True, maximum=200)):
                        raise StrategyError("Query embedding call budget reached; retry in 15 minutes")
                    try:
                        with trace.span("query_embedding", "Embed search query", query=query, model=self.embedding_model) as stage:
                            vector = self.provider.embed(self.embedding_model, [query])[0]
                            stage.outputs.update(dimensions=len(vector))
                    except ProviderError:
                        warnings.append("Query embedding failed; keyword and OCR-tolerant retrieval used.")
                found, channels = self.retrieval.search(rows, query, revision=self.revision, mode=profile.retrieval,
                    top_k=top_k, query_vector=vector, embedding_model=self.embedding_model, observer=trace.observe)
                mode = "hybrid" if "semantic" in channels and len(channels) > 1 else "semantic" if channels == ["semantic"] else "lexical"
                modes.append(mode)
                if profile.retrieval == "hybrid" and "semantic" not in channels:
                    warnings.append("Hybrid used keyword/OCR retrieval; no compatible semantic results were available.")
                evidence = []
                for row in found:
                    doc = document_map[row["file_id"]]
                    extraction = doc.get("metadata", {}).get("primary_extraction_id")
                    representation = "extraction:" + extraction if extraction else "canonical"
                    item = Evidence(row["chunk_id"], row["file_id"], row["text"], row["source_relpath"],
                        representation, row["char_start"], row["char_end"], deepcopy(row.get("source_origin") or {}), str(self.revision))
                    row_map[item.id] = {**row, "representation": representation}
                    evidence.append(item)
                search_stage.outputs.update(output_count=len(evidence), channels=channels, retrieval_mode=mode)
            self.guard()
            return evidence

        def decide(context):
            self.guard()
            with trace.span("decision", "Choose answer, follow-up search, or abstention",
                            input_count=len(context.evidence), can_retrieve=context.can_retrieve) as stage:
                if not context.evidence:
                    decision = Decision("abstain")
                elif not self.model:
                    selected = context.evidence[:5]
                    decision = Decision("answer", answer="Source excerpts (extractive baseline):\n\n" +
                        "\n\n".join(item.text[:2000] for item in selected),
                        citation_ids=tuple(item.id for item in selected), model="extractive")
                else:
                    if (not self.store.login_allowed("chat:" + self.account["id"], failed=True)
                            or not self.store.login_allowed("chat:global", failed=True, maximum=100)):
                        raise StrategyError("Chat call budget reached; retry in 15 minutes")
                    messages = decision_messages(context)
                    with trace.span("generation", "Ask configured chat model", model=self.model, messages=messages,
                                    response_format=decision_response_format(), temperature=0,
                                    output_token_limit=context.max_output_tokens) as generation:
                        calls.append({"model": self.model, "status": "started", "usage": {}})
                        try:
                            content, usage = self.provider.chat(self.model, messages,
                                                               max_tokens=context.max_output_tokens,
                                                               temperature=0,
                                                               response_format=decision_response_format())
                        except ProviderError as exc:
                            calls[-1]["status"] = "error"
                            raise StrategyError("Chat endpoint failed: " + str(exc)) from None
                        calls[-1].update(status="completed", usage=usage)
                        generation.outputs.update(model=self.model, usage=usage, response=content[:16000], response_truncated=len(content) > 16000)
                        decision = parse_decision(content, model=self.model, usage=usage)
                stage.outputs.update(action=decision.action, follow_up_query=decision.query,
                                     citation_ids=list(decision.citation_ids), model=decision.model)
            self.guard()
            return decision

        def rerank(request):
            self.guard()
            if (not self.store.login_allowed("rerank:" + self.account["id"], failed=True, maximum=20)
                    or not self.store.login_allowed("rerank:global", failed=True, maximum=200)):
                raise StrategyError("Reranking call budget reached; retry in 15 minutes")
            return self.reranker(request)

        try:
            with trace.span("rag_run", "Run " + profile.name, query=self.question.text, scope=self.scope,
                            corpus_revision=self.revision, profile=asdict(profile), input_count=len(self.rows)) as root:
                experiment = run_profile(self.question, profile, retrieve=retrieve, decide=decide,
                                         reranker=rerank if self.reranker else None, trace=trace)
                result = experiment.result
                self.guard()
                root.outputs.update(stop_reason=result.stop_reason, output_count=len(result.citations))
        except CorpusChanged:
            raise
        except (StrategyError, ProviderError) as exc:
            error = str(exc)
        citations = []
        if result:
            for item in result.citations:
                row = row_map[item.id]
                citations.append({**{key: row.get(key) for key in ("file_id", "filename", "source_relpath", "chunk_id", "char_start", "char_end", "source_origin", "representation")},
                                  "snippet": item.text[:700], "page": (item.source_origin or {}).get("page")})
        self.guard()
        usage_note = "Chat usage is reported when supplied by the endpoint; query embedding and reranker tokens/cost are not included."
        return {"answer": result.answer if result else "This run failed before producing a verified answer.",
                "citations": citations, "provider": "openai" if self.model else "extractive", "model": self.model or "extractive",
                "fallback_used": False, "profile_id": identifier, "retrieval_mode": modes[-1] if modes else "empty",
                "status": "error" if error else "ok", "error": error, "corpus_revision": self.revision,
                "agent_trace": trace.export(detailed=self.account["role"] == "admin", corpus_revision=self.revision,
                    scope=self.scope, query=self.question.text, stop_reason=result.stop_reason if result else "error",
                    chat_calls=len(calls), chat_usage=calls if self.account["role"] == "admin" else [],
                    warnings=list(dict.fromkeys(warnings)), usage_scope=usage_note,
                    evaluation={"recall": None, "answer_correctness": None, "note": "Not measured for this live run; requires labeled evidence or review."})}
