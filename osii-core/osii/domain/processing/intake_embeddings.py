"""Schedule saved-text embeddings independently of optional intake processors."""

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from queue import Empty, Queue

from osii.domain.model_provider_config import selected_model
from osii.domain.processing.standalone import validate_embedding_binding
from osii.domain.processing.jobs import (
    intake_embedding_receipt,
    intake_embedding_should_stop,
    save_intake_embedding_receipt,
)
from osii.indexing.incremental import IncrementalEmbeddingError, embed_selected_documents
from osii.processor_sdk.diagnostics import redact


def progress_report(receipt):
    completed = sorted(receipt["completed"])
    running = receipt["running"]
    failures = receipt["failures"]
    return {
        "completed_file_ids": completed,
        "running_file_ids": running,
        "completed_documents": len(completed),
        "total_documents": len(set(completed) | set(running) | failures.keys()),
        "embedded_chunks": receipt["embedded_chunks"],
        "reused_chunks": receipt["reused_chunks"],
        "failures": failures,
    }


def run_with_embedding_progress(run):
    if run.get("status") not in {"running", "pausing", "cancelling"}:
        return run
    receipt = intake_embedding_receipt(run["id"])
    if receipt is None:
        return run
    progress = progress_report(receipt)
    ready = {item["file_id"] for item in run["items"] if item.get("text_ready") and item.get("file_id")}
    return {
        **run,
        "indexing_status": "running" if progress["running_file_ids"] else "pending",
        "embedding_target": receipt.get("identity"),
        "indexing_progress": {**progress, "total_documents": max(len(ready), progress["total_documents"])},
    }


class IntakeEmbeddings:
    def __init__(self, root, job, run):
        self.root = root
        self.job = job
        self.payload = job["payload"]
        self.run_id = job["run_id"]
        self.retry = run.get("retry_stage") in {"all", "embedding"}
        self.receipt = intake_embedding_receipt(self.run_id) or {
            "identity": run.get("embedding_target"), "completed": [], "failures": {},
            "running": [], "embedded_chunks": 0, "reused_chunks": 0,
        }
        self.receipt["running"] = []
        self.ready = Queue()
        self.submitted = set()

    def submit(self, file_id, revision):
        entry = (file_id, revision)
        if not file_id or entry in self.submitted:
            return
        self.submitted.add(entry)
        self.ready.put(entry)

    def stopped(self):
        return intake_embedding_should_stop(self.job)

    def save(self):
        save_intake_embedding_receipt(self.run_id, self.receipt, self.job)

    def __enter__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="intake-index")
        self.future = self.executor.submit(copy_context().run, self._consume)
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.ready.put(None)
        self.executor.shutdown(wait=True)
        if exc is None:
            self.future.result()

    def _consume(self):
        last = False
        while not last and not self.stopped():
            first = self.ready.get()
            if first is None:
                break
            batch = [first]
            while len(batch) < 32:
                try:
                    file_id = self.ready.get_nowait()
                except Empty:
                    break
                if file_id is None:
                    last = True
                    break
                batch.append(file_id)
            revisions = self.receipt.setdefault("revisions", {})
            completed = set(self.receipt["completed"])
            failures = self.receipt["failures"]
            pending = []
            for file_id, revision in dict(batch).items():
                if revisions.get(file_id) != revision:
                    completed.discard(file_id)
                    failures.pop(file_id, None)
                if file_id not in completed and (self.retry or file_id not in failures):
                    pending.append(file_id)
                    revisions[file_id] = revision
            if pending and not self.stopped():
                self._embed(pending, completed, failures)

    def _embed(self, pending, completed, failures):
        self.receipt["running"] = pending
        self.save()
        for file_id in pending:
            failures.pop(file_id, None)
        payload = self.payload
        try:
            if payload.get("embedding_binding"):
                validate_embedding_binding(self.root, payload)
            report = embed_selected_documents(
                self.root, pending,
                model=(payload.get("embedding_binding") or {}).get("model")
                or payload.get("embedding_model") or selected_model("embedder", osii_root=self.root),
                batch_size=int(payload.get("embedding_batch_size", 64)),
                chunking_method=payload.get("chunking_method") or "sentence_window",
                chunk_size=int(payload.get("chunk_size", 768)),
                chunk_overlap=int(payload.get("chunk_overlap", 128)),
                expected_identity=self.receipt["identity"],
                should_stop=self.stopped,
            )
        except IncrementalEmbeddingError as exc:
            report = exc.report
        except Exception as exc:
            report = {"failures": {file_id: redact(str(exc)) for file_id in pending}}
        self.receipt["identity"] = report.get("identity") or self.receipt["identity"]
        completed.update(report.get("completed_file_ids", []))
        self.receipt["completed"] = sorted(completed)
        self.receipt["running"] = []
        failures.update({file_id: redact(error) for file_id, error in report["failures"].items()})
        for key in ("embedded_chunks", "reused_chunks"):
            self.receipt[key] += report.get(key, 0)
        self.save()
