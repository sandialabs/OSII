"""Transactional commits over the existing hosted schema, without migrations.

Only this adapter imports SQLAlchemy. No hosted startup, accounts, or filesystem
fallback are required by the shared processing contract.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
import json
import uuid

from osii.domain.storage.commits import (CommitConflict, CommitReceipt, JobCheckpoint,
    ProcessingCommit, ScopeProcessingCommit, ScopeInputRevision, InputRevision,
    embedding_identity, extraction_material, text_digest)
from osii.processor_sdk import EmbeddingResponse, ExtractionResponse, SynthesisResponse


class PostgresProcessingCommitter:
    def __init__(self, engine, *, actor_id: str | None = None):
        if engine.dialect.name != "postgresql":
            raise ValueError("PostgresProcessingCommitter requires PostgreSQL")
        self.engine = engine
        self.actor_id = actor_id

    @staticmethod
    def _sql(conn, query, **values):
        from sqlalchemy import text
        return conn.execute(text(query), values)

    def _lease(self, conn, checkpoint: JobCheckpoint):
        row = self._sql(conn, """SELECT payload FROM jobs WHERE id=:id AND worker_id=:worker
            AND status IN ('running','pausing','cancelling') AND lease_until>CURRENT_TIMESTAMP FOR UPDATE""",
            id=checkpoint.job_id, worker=checkpoint.worker_id).mappings().first()
        if row is None:
            raise CommitConflict("Worker no longer owns this processing run")
        return row["payload"]

    def commit(self, command: ProcessingCommit | ScopeProcessingCommit, *, checkpoint: JobCheckpoint | None = None) -> CommitReceipt:
        command.validate()
        if checkpoint and ((checkpoint.index is None) != (checkpoint.item is None)):
            raise ValueError("Checkpoint index and item must be supplied together")
        fingerprint = command.fingerprint()
        key = "processing_commit:" + command.commit_id
        with self.engine.begin() as conn:
            scoped = isinstance(command, ScopeProcessingCommit)
            if scoped:
                # Membership predicates and full-text revisions must come from
                # one coherent snapshot, including concurrent new documents.
                self._sql(conn, "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            lock = (f"scope:{command.scope.kind}:{command.scope.identifier}" if scoped else command.file_id)
            self._sql(conn, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", key="osii-processing:" + lock)
            job_payload = self._lease(conn, checkpoint) if checkpoint else None
            if scoped:
                actor = self.actor_id or (job_payload or {}).get("actor_id")
                current = self._scope_current(conn, command.scope, actor, len(command.input_revision.member_ids) + 1)
            saved = self._sql(conn, "SELECT value FROM settings WHERE id=:key", key=key).scalar()
            if saved:
                if saved["fingerprint"] != fingerprint:
                    raise CommitConflict("Operation ID was already used for a different result")
                receipt = replace(CommitReceipt(**saved["receipt"]), replayed=True)
            elif scoped:
                command.input_revision.verify_current(current)
                result = self._scope_products(conn, command, actor)
                receipt = CommitReceipt(command.commit_id, None, command.kind, result,
                    scope_type=command.scope.kind, scope_id=command.scope.identifier)
                self._sql(conn, "INSERT INTO settings(id,value) VALUES (:key,CAST(:value AS jsonb))",
                    key=key, value=json.dumps({"fingerprint": fingerprint, "receipt": asdict(receipt)}))
            else:
                doc = self._sql(conn, "SELECT * FROM documents WHERE file_id=:id FOR UPDATE", id=command.file_id).mappings().first()
                if command.input_revision:
                    if doc is None or not doc["active"]:
                        raise CommitConflict("No active input document is available")
                    primary = doc["metadata"].get("primary_extraction_id")
                    if primary is None:
                        primary = self._sql(conn, "SELECT id FROM extractions WHERE file_id=:id ORDER BY created_at DESC,id LIMIT 1", id=command.file_id).scalar() or "canonical"
                    expected = command.input_revision
                    if primary != expected.representation_id or text_digest(doc["text"]) != expected.text_sha256:
                        raise CommitConflict("Preferred text changed; stage a new processing step")
                if isinstance(command.response, ExtractionResponse):
                    result = self._extract(conn, command, doc)
                elif isinstance(command.response, EmbeddingResponse):
                    result = self._embed(conn, command, doc)
                else:
                    result = self._product(conn, command, checkpoint)
                receipt = CommitReceipt(command.commit_id, command.file_id, command.kind, result)
                self._sql(conn, "INSERT INTO settings(id,value) VALUES (:key,CAST(:value AS jsonb))",
                    key=key, value=json.dumps({"fingerprint": fingerprint, "receipt": asdict(receipt)}))
            if checkpoint and checkpoint.index is not None:
                if not 0 <= checkpoint.index < len(job_payload.get("items", [])):
                    raise ValueError("Checkpoint item is outside the processing run")
                job_payload["items"][checkpoint.index] = checkpoint.item
                self._sql(conn, "UPDATE jobs SET payload=CAST(:body AS jsonb) WHERE id=:id",
                    id=checkpoint.job_id, body=json.dumps(job_payload))
        return receipt

    def _scope_current(self, conn, scope, actor, limit):
        where, values = "d.active", {"identity": scope.identifier, "actor": actor, "limit": limit}
        if scope.kind == "object":
            where += " AND d.file_id=:identity"
        elif scope.kind == "folder" and scope.identifier.strip("/") not in {"", "."}:
            prefix = scope.identifier.strip("/")
            where += ' AND d.source_relpath COLLATE "C" >= :lower AND d.source_relpath COLLATE "C" < :upper'
            values.update(lower=prefix + "/", upper=prefix + "0")
        elif scope.kind == "collection":
            collection = self._sql(conn, """SELECT members FROM collections WHERE id=:identity
                AND (visibility='shared' OR owner_id=:actor) FOR SHARE""", **values).mappings().first()
            if collection is None:
                raise CommitConflict("Collection is unavailable to this processing context")
            where += " AND d.file_id IN (SELECT jsonb_array_elements_text(CAST(:members AS jsonb)))"
            values["members"] = json.dumps(collection["members"])
        rows = self._sql(conn, f"""SELECT d.file_id,encode(sha256(convert_to(d.text,'UTF8')),'hex') AS text_sha256,
            COALESCE(d.metadata->>'primary_extraction_id',
            (SELECT e.id FROM extractions e WHERE e.file_id=d.file_id ORDER BY e.created_at DESC,e.id LIMIT 1),
            'canonical') AS representation_id FROM documents d WHERE {where}
            ORDER BY d.file_id COLLATE "C" LIMIT :limit FOR SHARE""", **values).mappings().all()
        return ScopeInputRevision(tuple(row["file_id"] for row in rows), tuple(
            InputRevision(row["file_id"], row["representation_id"], row["text_sha256"]) for row in rows))

    def _scope_products(self, conn, command, actor):
        """Use the existing hosted scope-product/revision tables and addresses."""
        import hashlib
        response = command.response
        if isinstance(response, SynthesisResponse):
            outputs = [{"id": "wiki", "family": "synthesis", "data": {
                "artifact_type": "wiki_markdown",
                "title": f"{command.provenance.get('scope_title') or command.scope.identifier} · {response.processor.display_name}",
                "markdown": response.markdown,
                "citations": [row.model_dump(mode="json") for row in response.citations]}}]
        else:
            outputs = [{"id": item.id, "family": "enrichment", "data": item.standard_data.model_dump(mode="json")}
                       for item in response.artifacts]
        provenance = {**command.provenance, "commit_id": command.commit_id,
            "commit_fingerprint": command.fingerprint(), "processing_input": asdict(command.input_revision),
            "processor": response.processor.model_dump(mode="json"), "config": command.request.config,
            "expert_context": command.request.expert_context, "response_metadata": response.metadata,
            "warnings": response.warnings}
        results = []
        for output in outputs:
            name = "tool-" + hashlib.sha256(f"{response.processor.name}:{output['id']}".encode()).hexdigest()[:24] + ".json"
            data = output["data"]
            self._sql(conn, """INSERT INTO scope_products(id,scope_type,scope_id,filename,family,method,title,artifact_type)
                VALUES (:id,:kind,:scope,:name,:family,:method,:title,:type)
                ON CONFLICT ON CONSTRAINT scope_product_address DO NOTHING""",
                id=str(uuid.uuid4()), kind=command.scope.kind, scope=command.scope.identifier, name=name,
                family=output["family"], method=response.processor.name, title=data.get("title", output["id"]), type=data["artifact_type"])
            product = self._sql(conn, """SELECT * FROM scope_products WHERE scope_type=:kind AND scope_id=:scope
                AND filename=:name FOR UPDATE""", kind=command.scope.kind, scope=command.scope.identifier, name=name).mappings().one()
            parent = (product["current_revision"] if command.product_parents is None
                      else command.product_parents.get(name))
            current_origin = self._sql(conn, "SELECT origin FROM scope_revisions WHERE id=:id", id=product["current_revision"]).scalar()
            revision = str(uuid.uuid5(uuid.NAMESPACE_URL, f"osii:scope-product:{command.commit_id}:{output['id']}"))
            self._sql(conn, """INSERT INTO scope_revisions(id,product_id,parent,origin,created_at,actor_id,data,provenance)
                VALUES (:id,:product,:parent,'generated',:created,:actor,CAST(:data AS jsonb),CAST(:provenance AS jsonb))""",
                id=revision, product=product["id"], parent=parent, created=datetime.now(UTC).isoformat(), actor=actor,
                data=json.dumps(data), provenance=json.dumps(provenance))
            if product["current_revision"] is None or (product["current_revision"] == parent and current_origin != "human"):
                self._sql(conn, "UPDATE scope_products SET current_revision=:revision,title=:title,artifact_type=:type WHERE id=:id",
                    revision=revision, title=data.get("title", product["title"]), type=data["artifact_type"], id=product["id"])
            results.append({"filename": name, "revision_id": revision, "family": output["family"]})
        return {"products": results, "scope_type": command.scope.kind, "scope_id": command.scope.identifier}

    def _extract(self, conn, command, previous):
        source, response = command.source, command.response
        text, spans = extraction_material(command)
        primary = command.make_primary or previous is None
        if previous is not None and previous["sha256"] != source.sha256:
            raise CommitConflict("Document ID already belongs to different source bytes")
        if primary:
            self._sql(conn, "UPDATE documents SET active=false WHERE source_relpath=:path AND file_id<>:id",
                path=source.source_relpath, id=command.file_id)
            metadata = {**source.metadata, "segments": spans, "extractor": response.processor.model_dump(mode="json"),
                "primary_extraction_id": command.commit_id, "processing_commit_id": command.commit_id,
                "extraction_config": command.request.config, "extraction_expert_context": command.request.expert_context,
                "processing_provenance": command.provenance}
            self._sql(conn, """INSERT INTO documents(file_id,source_relpath,active,sha256,filename,media_type,size_bytes,text,metadata,updated_at)
                VALUES (:id,:path,true,:sha,:name,:media,:size,:text,CAST(:meta AS jsonb),CURRENT_TIMESTAMP)
                ON CONFLICT(file_id) DO UPDATE SET source_relpath=excluded.source_relpath, active=true,
                sha256=excluded.sha256,filename=excluded.filename,media_type=excluded.media_type,
                size_bytes=excluded.size_bytes,text=excluded.text,metadata=excluded.metadata,updated_at=excluded.updated_at""",
                id=command.file_id, path=source.source_relpath, sha=source.sha256, name=source.filename,
                media=source.media_type, size=source.size_bytes, text=text, meta=json.dumps(metadata))
            self._sql(conn, "DELETE FROM chunks WHERE file_id=:id", id=command.file_id)
            for row in command.chunks:
                self._sql(conn, """INSERT INTO chunks(chunk_id,file_id,text,char_start,char_end,source_origin,embedding,embedding_model)
                    VALUES (:chunk,:id,:text,:start,:end,CAST(:origin AS jsonb),CAST(:vector AS jsonb),:model)""",
                    chunk=row["chunk_id"], id=command.file_id, text=row["text"], start=row["char_start"], end=row["char_end"],
                    origin=json.dumps(row.get("source_origin", {})), vector=json.dumps(row.get("embedding")), model=row.get("embedding_model"))
            self._sql(conn, """DELETE FROM artifacts WHERE file_id=:id AND kind NOT IN
                ('synthesis','enrichment','manual_metadata','manual_metadata_history')""", id=command.file_id)
            for artifact in response.artifacts:
                output_id = str(uuid.uuid5(uuid.NAMESPACE_URL, command.commit_id + ":" + artifact.id))
                self._sql(conn, "INSERT INTO artifacts(id,file_id,kind,payload) VALUES (:output,:id,:kind,CAST(:payload AS jsonb))",
                    output=output_id, id=command.file_id, kind=artifact.kind, payload=artifact.model_dump_json())
            self._sql(conn, "UPDATE datasets SET revision=revision+1 WHERE id='shared'")
        self._sql(conn, "INSERT INTO extractions(id,file_id,sha256,response,created_at) VALUES (:id,:file_id,:sha,CAST(:response AS jsonb),CURRENT_TIMESTAMP)",
            id=command.commit_id, file_id=command.file_id, sha=source.sha256, response=response.model_dump_json())
        return {"variant_id": command.commit_id, "made_primary": primary}

    def _product(self, conn, command, checkpoint):
        response = command.response
        checkpoint_provenance = dict(command.provenance)
        payload = {"response": response.model_dump(mode="json"), "processor_kind": response.processor.kind.value,
            "created_at": datetime.now(UTC).isoformat(), "input_extraction_id": command.input_revision.representation_id,
            "input_text_sha256": command.input_revision.text_sha256, "config": command.request.config,
            "expert_context": command.request.expert_context, **checkpoint_provenance,
            "commit_id": command.commit_id}
        output_id = (str(uuid.uuid5(uuid.NAMESPACE_URL, f"osii:{checkpoint.job_id}:{checkpoint.index}:{command.kind}"))
                     if checkpoint and checkpoint.index is not None else command.commit_id)
        self._sql(conn, "INSERT INTO artifacts(id,file_id,kind,payload) VALUES (:id,:file_id,:kind,CAST(:payload AS jsonb))",
            id=output_id, file_id=command.file_id, kind=command.kind, payload=json.dumps(payload))
        return {"output_id": output_id}

    def _embed(self, conn, command, doc):
        response = command.response
        identity = embedding_identity(response)
        self._sql(conn, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))",
            key="osii-vector-space:" + response.model)
        rows = self._sql(conn, "SELECT chunk_id,text FROM chunks WHERE file_id=:id ORDER BY char_start,chunk_id FOR UPDATE", id=command.file_id).mappings().all()
        by_id = {row["chunk_id"]: row["text"] for row in rows}
        if set(by_id) != {row.id for row in command.request.inputs}:
            raise CommitConflict("Embedding commit requires the complete current document chunk set")
        if any(by_id[row.id] != row.text for row in command.request.inputs):
            raise CommitConflict("Chunk text changed during embedding")
        others = self._sql(conn, """SELECT metadata->'embedding_identity' AS identity FROM documents
            WHERE active AND file_id<>:id AND metadata->>'embedding_model'=:model""",
            id=command.file_id, model=response.model).mappings()
        if any(row["identity"] and row["identity"] != identity for row in others):
            raise CommitConflict("Embedding vector space changed; rebuild the index before activating it")
        for row in response.vectors:
            self._sql(conn, "UPDATE chunks SET embedding=CAST(:vector AS jsonb),embedding_model=:model WHERE file_id=:id AND chunk_id=:chunk",
                id=command.file_id, chunk=row.id, model=response.model, vector=json.dumps(row.vector))
        metadata = {**doc["metadata"], "embedding_model": response.model, "embedding_warning": "",
                    "embedding_identity": identity, "embedding_commit_id": command.commit_id,
                    "embedding_provenance": {"processor": response.processor.model_dump(mode="json"),
                        "input_revision": asdict(command.input_revision), "config": command.request.config,
                        "metadata": response.metadata}}
        self._sql(conn, "UPDATE documents SET metadata=CAST(:meta AS jsonb),updated_at=CURRENT_TIMESTAMP WHERE file_id=:id",
            id=command.file_id, meta=json.dumps(metadata))
        self._sql(conn, "UPDATE datasets SET revision=revision+1 WHERE id='shared'")
        return {"identity": identity, "count": len(response.vectors)}
