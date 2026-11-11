"""Standalone composition: selected-library retrieval and configured models over shared RAG.

Read guards detect index/config/membership changes; this is not a transactional
snapshot of a concurrently edited filesystem. No rebuild or configuration writes
are initiated by profile selection.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path

from osii.configuration import models_path, tools_path
from osii.domain.scopes.search import build_scope_filters, file_matches_scope
from osii.domain.services.search import dashboard_search
from osii.rag.config import get_chat_settings
from osii.rag.generation import complete_experiment_messages
from osii.rag.models import ChatRequest, ChatResponse, CitationModel, CompareRequest, ComparedRun, ComparisonResponse
from osii.rag.strategies import Decision, Evidence, Question, Scope, StrategyError
from osii.rag.strategies.decisions import decision_messages, parse_decision
from osii.rag.strategies.experiments import run_profile
from osii.rag.strategies.profiles import PROFILES, get_profile


class CorpusChanged(StrategyError):
    pass


def _model(settings):
    primary = settings.chat_provider_chain[0]
    model = settings.ollama_chat_model if primary == "ollama" else settings.openai_chat_model or settings.chat_model
    return primary, model if primary != "extractive" else "extractive"


def profile_catalog(root: Path, reranker=None) -> dict:
    settings = get_chat_settings(root)
    primary, model = _model(settings)
    installed = importlib.util.find_spec("haystack") is not None
    items = []
    for profile in PROFILES:
        reason = None
        if not installed:
            reason = "Install the rag-haystack extra or restart with make dev."
        elif profile.rerank and reranker is None:
            reason = "No Core RAG reranker is configured. See the RAG authoring guide."
        elif profile.strategy == "iterative" and primary == "extractive":
            reason = "Select a chat model in Setup for iterative query planning."
        items.append({**asdict(profile), "available": reason is None, "unavailable_reason": reason})
    return {"profiles": items, "chat_model": model, "provider": primary}


class _Session:
    def __init__(self, root: Path, request, reranker=None, library=None):
        self.library = library
        self.root, self.scope, self.reranker = root.resolve(), deepcopy(request.scope.model_dump()), reranker
        self.question = Question(request.query, Scope(self.scope["scope_type"],
            self.scope.get({"folder": "folder_id", "collection": "collection_id", "object": "file_id"}.get(self.scope["scope_type"], "")) or ""),
            tuple((turn.role, turn.content) for turn in request.history))
        self.settings = get_chat_settings(root)
        self.primary, self.model = _model(self.settings)
        self.filters = (frozenset(d.file_id for d in library.documents(self.scope))
                        if library is not None else build_scope_filters(root, self.scope))
        if library is None and self.scope["scope_type"] == "folder" and self.filters["folder_relpath"] is None:
            raise StrategyError("Folder scope was not found; an experiment cannot broaden to root")
        self.initial = self._signature()
        self.corpus_check = hashlib.sha256(repr(self.initial).encode()).hexdigest()[:20]
        self.rows, self.object_guards, self.evidence_records = {}, {}, {}
        self.available = {item["id"]: item for item in profile_catalog(root, reranker)["profiles"]}

    @staticmethod
    def _stat(path):
        try:
            stat = path.stat()
            return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
        except FileNotFoundError:
            return None

    def _signature(self):
        if self.library is not None:
            from osii.domain.processing.postgres_workflow import configuration_stamp
            revision = self.library.query("SELECT revision FROM datasets WHERE id='shared'")[0]["revision"]
            return (revision, configuration_stamp(self.root), tuple(d.file_id for d in self.library.documents(self.scope)))
        folder = self.root / "embeddings"
        paths = [folder / "chunks/chunks.jsonl", models_path(), tools_path(), *folder.glob("segments.*"), *folder.glob("providers/*/*/segments.*")]
        return tuple((str(p), self._stat(p)) for p in sorted(set(paths)))

    def guard(self):
        if self._signature() != self.initial or (self.library is None and build_scope_filters(self.root, self.scope) != self.filters):
            raise CorpusChanged("The corpus, scope membership, or model configuration changed. Start a new comparison.")
        for path, stat in self.object_guards.items():
            if self._stat(path) != stat:
                raise CorpusChanged("A retrieved document changed. Start a new comparison.")

    def indexed_passages(self, rows: list[dict]) -> dict:
        """Read exact indexed text, never the search UI's truncated preview."""
        wanted = {(row["file_id"], row.get("chunk_id")) for row in rows}
        passages = {}
        if not wanted:
            return passages
        if self.library is not None:
            for row in self.rows_for_query:
                key=(row["file_id"],row.get("chunk_id"))
                if key in wanted:
                    passages[key]=row
            if set(passages)!=wanted:
                raise StrategyError("A search hit has no matching PostgreSQL passage")
            return passages
        with (self.root / "embeddings/chunks/chunks.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict):
                    continue
                key = (record.get("file_id"), record.get("chunk_id"))
                if key in wanted:
                    passages[key] = record
        if set(passages) != wanted:
            raise StrategyError("A search hit has no matching indexed passage; refresh the search index in Intake")
        return passages

    def run(self, identifier: str) -> ChatResponse:
        profile = get_profile(identifier)
        capability = self.available[identifier]
        if not capability["available"]:
            raise StrategyError(capability["unavailable_reason"])
        actual_modes, calls = [], []
        self.guard()

        def retrieve(query, *, top_k):
            self.guard()
            manifest = self.root / "embeddings/chunks/chunks.jsonl"
            if self.library is not None:
                from osii.domain.storage.retrieval import RetrievalRequest
                found=self.library.retrieve(RetrievalRequest(query,self.library.scope(self.scope),profile.retrieval,top_k))
                mode,rows=found.actual_mode,found.legacy_rows()
                self.rows_for_query=deepcopy(rows)
            elif not manifest.is_file():
                mode, rows = "empty", []
            else:
                mode, rows = dashboard_search(self.root, query=query, mode=profile.retrieval, top_k=top_k, scope=deepcopy(self.scope))
            rows = [row for row in rows[:top_k] if (row["file_id"] in self.filters if self.library is not None else
                file_matches_scope(file_id=row["file_id"],source_relpath=row.get("source_relpath", ""),scope_filters=self.filters))]
            passages = self.indexed_passages(rows)
            values = []
            for row in rows:
                key = row.get("chunk_id")
                if not key:
                    raise StrategyError("Experiment evidence requires a stable indexed chunk ID")
                passage = passages[(row["file_id"], key)]
                if any(row.get(field) != passage.get(field) for field in ("char_start", "char_end")):
                    raise StrategyError("Search spans differ from the chunk index; refresh the search index in Intake")
                representation = passage.get("source_text_representation") or "preferred"
                if passage.get("source_extraction_id"):
                    representation += ":" + passage["source_extraction_id"]
                eid = f'{row["file_id"]}|{representation}|{key}'
                value = Evidence(eid, row["file_id"], passage["text"], passage.get("source_relpath", ""), representation,
                    passage.get("char_start"), passage.get("char_end"), deepcopy(row.get("source_origin") or {}), self.corpus_check)
                if eid in self.evidence_records and self.evidence_records[eid] != value:
                    raise CorpusChanged("A retrieved passage changed. Start a new comparison.")
                self.evidence_records[eid] = value
                self.rows[eid] = deepcopy(row)
                values.append(value)
                if self.library is not None:
                    continue
                directory = self.root / "objects" / row["file_id"]
                if not directory.resolve().is_relative_to(self.root / "objects"):
                    raise StrategyError("Invalid document identity")
                for path in (directory / "text.txt", directory / "meta.toml", directory / "manifest.jsonl",
                             directory / "edited_text.json", directory / "extractions/index.json"):
                    self.object_guards.setdefault(path, self._stat(path))
            self.guard()
            actual_modes.append(mode)
            return values

        def decide(context):
            self.guard()
            if not context.evidence:
                return Decision("abstain", model=self.model)
            if self.primary == "extractive":
                return Decision("answer", answer="Source excerpts (extractive baseline):\n\n" + "\n\n".join(e.text for e in context.evidence[:5]),
                    citation_ids=tuple(e.id for e in context.evidence[:5]), model="extractive")
            content, usage, model = complete_experiment_messages(provider=self.primary, settings=self.settings,
                model=self.model, messages=decision_messages(context), max_tokens=min(900, self.settings.chat_max_tokens))
            calls.append({"model": model, "usage": usage})
            self.guard()
            return parse_decision(content, model=model, usage=usage)

        experiment = run_profile(self.question, profile, retrieve=retrieve, decide=decide, reranker=self.reranker)
        self.guard()
        result = experiment.result
        citations = [CitationModel(**{k: self.rows[e.id].get(k) for k in
            ("file_id", "filename", "source_relpath", "snippet", "chunk_id", "segment_id", "page", "char_start", "char_end", "source_origin")}, representation=e.representation) for e in result.citations]
        warnings = []
        if profile.retrieval == "hybrid" and "lexical" in actual_modes:
            warnings.append("Hybrid retrieval used a keyword fallback; compatible semantic results were unavailable.")
        if "empty" in actual_modes:
            warnings.append("No chunk index is available. Process documents in Intake before comparing retrieval quality.")
        trace = {**asdict(experiment), "profile": asdict(profile), "corpus_check": self.corpus_check,
            "consistency": "postgres-revision-guard" if self.library is not None else "local-read-guard", "actual_retrieval_modes": actual_modes, "chat_calls": len(calls),
            "chat_usage": calls, "reranker_calls": sum(event.reranker_called for event in experiment.retrieval),
            "usage_scope": "Chat calls are measured; query embedding and custom reranker token usage is not reported by these adapters.", "warnings": warnings}
        return ChatResponse(answer=result.answer, citations=citations, provider=self.primary, model=calls[-1]["model"] if calls else self.model,
            retrieval_mode="hybrid" if "hybrid" in actual_modes else actual_modes[0] if actual_modes else "empty",
            profile_id=profile.id, experiment=trace)


def answer_experiment(root: Path, request: ChatRequest, *, reranker=None, library=None) -> ChatResponse:
    return _Session(root, request, reranker, library).run(request.profile_id)


def compare_profiles(root: Path, request: CompareRequest, *, reranker=None, library=None) -> ComparisonResponse:
    session = _Session(root, request, reranker, library)
    for identifier in request.profile_ids:
        get_profile(identifier)
        if not session.available[identifier]["available"]:
            raise StrategyError(session.available[identifier]["unavailable_reason"])
    runs = []
    for identifier in request.profile_ids:
        try:
            response = session.run(identifier)
            runs.append(ComparedRun(profile_id=identifier, status="ok", response=response))
        except CorpusChanged:
            raise
        except StrategyError as exc:
            runs.append(ComparedRun(profile_id=identifier, status="error", error=str(exc)))
    session.guard()
    return ComparisonResponse(query=request.query, scope=request.scope, corpus_check=session.corpus_check, model=session.model, runs=runs)
