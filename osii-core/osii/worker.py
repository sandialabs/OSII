"""Durable, local-only worker for OSII processing runs."""

from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from osii.domain.processing.jobs import (
    append_log,
    configure_job_store,
    get_run,
    heartbeat_worker,
    honor_run_control,
    register_worker,
    save_run,
    unregister_worker,
)


def execute_job(job: dict) -> None:
    from osii.api.runs_routes import run_worker

    payload = job["payload"]
    osii_root = Path(payload["osii_store"]).resolve()
    configure_job_store(osii_root)

    if payload.get("job_kind") == "tool":
        from osii.domain.tool_actions import execute_tool
        execute_tool(job)
        return

    run = get_run(job["run_id"])
    if payload.get("job_kind") == "full_index":
        if run and run.get("indexing_status") == "done":
            run["status"] = "done"
            save_run(run)
            return
        if honor_run_control(job["run_id"]):
            return
        from osii.domain.processing.standalone import validate_embedding_binding
        validate_embedding_binding(osii_root, payload)
    # An interrupted/retried embedding phase never repeats original reads,
    # extraction, summaries, or enrichment from the completed file phase.
    if not run or run.get("file_processing_status") != "done":
        run_worker(
            run_id=job["run_id"],
            resolved_files=[Path(path) for path in payload["resolved_files"]],
            queue_items=payload["queue_items"],
            include_subfolders=payload["include_subfolders"],
            include_patterns=payload["include_patterns"],
            exclude_patterns=payload["exclude_patterns"],
            context=payload["context"],
            intake_name=payload["intake_name"],
            data_volume_root=Path(payload["data_volume_root"]),
            osii_store=osii_root,
            shared_root=Path(payload["shared_root"]),
            upload_root=Path(payload["upload_root"]),
            parser_routes_path=Path(payload["parser_routes_path"]),
            shared_root_host_path=payload.get("shared_root_host_path") or None,
            synthesizer_name=payload.get("synthesizer_name") or None,
            synthesizer_config=payload.get("synthesizer_config") or {},
            extractor_overrides=payload.get("extractor_overrides") or {},
            workflow=payload.get("workflow") or "intake",
            run_extraction=bool(payload.get("run_extraction", True)),
            extract_mode=payload.get("extract_mode") or "always",
            extraction_policy=payload.get("extraction_policy") or "auto",
            enricher_name=payload.get("enricher_name") or None,
            enricher_config=payload.get("enricher_config") or {},
            collection_id=payload.get("collection_id") or None,
            staging=payload.get("staging"),
        )

    run = get_run(job["run_id"])
    if run and run.get("status") in {"paused", "cancelled"}:
        return

    if run and run.get("status") == "error":
        raise RuntimeError(run.get("error") or "Run failed")
    if run:
        run["file_processing_status"] = "done"
        save_run(run)

    if payload.get("build_embeddings"):
        from osii.indexing.incremental import (
            embed_selected_documents,
            IncrementalEmbeddingError,
        )
        from osii.domain.model_provider_config import selected_model

        run = get_run(job["run_id"])
        file_ids = run.get("indexing_file_ids")
        if file_ids is None:
            file_ids = sorted(
                {
                    item.get("file_id") or Path(item.get("osii", "")).name
                    for item in run["items"]
                    if item.get("status") in {"done", "partial"}
                    and (item.get("file_id") or item.get("osii"))
                }
            )
            run["indexing_file_ids"] = file_ids
        run.update(
            status="running",
            indexing_status="running",
            indexing_error=None,
            finished_at=None,
        )
        save_run(run)

        def progress(report):
            current = get_run(job["run_id"])
            current["embedding_target"] = report["identity"]
            current["indexing_progress"] = {
                key: value for key, value in report.items() if key != "identity"
            }
            if payload.get("job_kind") == "full_index":
                finished = set(report.get("completed_file_ids", []))
                current["completed"] = len(finished)
                for item in current["items"]:
                    item["status"] = "done" if item.get("file_id") in finished else "error" if item.get("file_id") in report["failures"] else "pending"
                    item["error"] = report["failures"].get(item.get("file_id"))
            save_run(current)

        try:
            if payload.get("job_kind") == "full_index" and not file_ids:
                raise ValueError("No documents are available to embed")
            report = embed_selected_documents(
                osii_root,
                file_ids,
                model=payload.get("embedding_model") or selected_model("embedder", osii_root=osii_root),
                batch_size=int(payload.get("embedding_batch_size", 64)),
                chunking_method=payload.get("chunking_method") or "sentence_window",
                chunk_size=int(payload.get("chunk_size", 768)),
                chunk_overlap=int(payload.get("chunk_overlap", 128)),
                expected_identity=run.get("embedding_target"),
                on_progress=progress,
                should_stop=lambda: honor_run_control(job["run_id"]),
                **({"rebuild_id": job["run_id"]} if payload.get("job_kind") == "full_index" else {}),
            )
            if report["paused"] or honor_run_control(job["run_id"]):
                run = get_run(job["run_id"])
                run["indexing_status"] = run["status"]
                save_run(run)
                return
            run = get_run(job["run_id"])
            run.update(
                status="done",
                indexing_status="done",
                error=None,
                error_phase=None,
                finished_at=datetime.now(UTC).isoformat(),
            )
            save_run(run)
            append_log(
                job["run_id"],
                "Full index saved." if payload.get("job_kind") == "full_index" else "Selected-document embeddings saved; existing library vectors preserved.",
            )
        except Exception as exc:
            run = get_run(job["run_id"])
            if run:
                run.update(
                    status="error",
                    indexing_status="error",
                    indexing_error=str(exc),
                    error=str(exc),
                    error_phase="embedding",
                    finished_at=datetime.now(UTC).isoformat(),
                )
                if isinstance(exc, IncrementalEmbeddingError):
                    run["indexing_progress"] = {
                        key: value
                        for key, value in exc.report.items()
                        if key != "identity"
                    }
                save_run(run)
            append_log(
                job["run_id"],
                f"Embeddings incomplete; retry will reuse saved vectors and completed file processing: {exc}",
            )
            raise

    run = get_run(job["run_id"])
    if run and run.get("status") == "error":
        raise RuntimeError(run.get("error") or "Run failed")
    if run:
        save_run(run)


def main() -> None:
    from osii.domain.storage.sidecar_jobs import SidecarJobStore
    from osii.domain.storage.job_store import JobOwnershipLost
    osii_root = Path(os.getenv("OSII_ROOT", "./data_volume/.osii")).resolve()
    configure_job_store(osii_root)
    queue = SidecarJobStore(osii_root)
    idle_seconds = min(
        5.0,
        max(0.2, float(os.getenv("OSII_WORKER_POLL_SECONDS", "1"))),
    )
    worker_id = uuid.uuid4().hex
    register_worker(worker_id)
    try:
        while True:
            heartbeat_worker(worker_id)
            claimed = queue.claim(worker_id)
            if claimed is None:
                time.sleep(idle_seconds)
                continue
            job = claimed.job.native
            def settle(outcome='done', error=None):
                try:
                    queue.finish(claimed.lease, outcome=outcome, error=error)
                except JobOwnershipLost:
                    pass  # Recovery owns the job now; never finish its newer claim.
            stop_heartbeat = threading.Event()

            def keep_job_alive(lease=claimed.lease) -> None:
                while not stop_heartbeat.wait(3):
                    heartbeat_worker(worker_id)
                    try:
                        queue.heartbeat(lease)
                    except JobOwnershipLost:
                        break

            heartbeat = threading.Thread(target=keep_job_alive, daemon=True)
            heartbeat.start()
            try:
                execute_job(job)
                honor_run_control(job["run_id"])
                run = get_run(job["run_id"])
                if run and run.get("control_state") == "cancel_requested":
                    run["status"] = "cancelled"
                    run["control_state"] = "cancelled"
                    run["finished_at"] = datetime.now(UTC).isoformat()
                    for item in run.get("items", []):
                        if item.get("status") in {"pending", "running"}:
                            item["status"] = "cancelled"
                    save_run(run)
                    settle('cancelled')
                elif run and run.get("control_state") == "pause_requested":
                    run["status"] = "paused"
                    run["control_state"] = "paused"
                    save_run(run)
                    settle('paused')
                elif run and run.get("status") == "paused":
                    settle('paused')
                elif run and run.get("status") == "cancelled":
                    settle('cancelled')
                else:
                    settle()
            except Exception as exc:
                settle('error', error=str(exc))
            finally:
                stop_heartbeat.set()
                heartbeat.join(timeout=4)
    finally:
        unregister_worker(worker_id)


if __name__ == "__main__":
    main()
