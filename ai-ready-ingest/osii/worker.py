"""Durable, local-only worker for OSII processing runs."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from osii.domain.processing.jobs import (
    append_log,
    cancel_queue_job,
    claim_next_queue_job,
    complete_queue_job,
    configure_job_store,
    get_run,
    pause_queue_job,
    save_run,
)


def execute_job(job: dict) -> None:
    from osii.api.runs_routes import run_worker

    payload = job["payload"]
    osii_root = Path(payload["osii_store"]).resolve()
    configure_job_store(osii_root)

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
        extraction_policy=payload.get("extraction_policy") or "make_primary",
        enricher_name=payload.get("enricher_name") or None,
        enricher_config=payload.get("enricher_config") or {},
    )

    run = get_run(job["run_id"])
    if run and run.get("status") in {"paused", "cancelled"}:
        return

    if payload.get("build_embeddings"):
        from osii.build_vector_index import main as build_vector_index_main
        import sys

        old_argv = sys.argv[:]
        sys.argv = [
            "build_vector_index",
            "--osii-root",
            str(osii_root),
            "--batch-size",
            str(payload.get("embedding_batch_size", 64)),
            "--chunking-method",
            str(payload.get("chunking_method") or "sentence_window"),
            "--chunk-size",
            str(payload.get("chunk_size", 768)),
            "--chunk-overlap",
            str(payload.get("chunk_overlap", 128)),
        ]
        try:
            run = get_run(job["run_id"])
            if run:
                run["indexing_status"] = "running"
                save_run(run)
            build_vector_index_main()
            append_log(job["run_id"], "Local search embeddings built.")
            run = get_run(job["run_id"])
            if run:
                run["indexing_status"] = "done"
                save_run(run)
        except Exception as exc:
            run = get_run(job["run_id"])
            if run:
                run["indexing_status"] = "error"
                run["indexing_error"] = str(exc)
                save_run(run)
            append_log(job["run_id"], f"Embedding backfill failed; extracted documents remain available: {exc}")
        finally:
            sys.argv = old_argv

    run = get_run(job["run_id"])
    if run and run.get("status") == "error":
        raise RuntimeError(run.get("error") or "Run failed")
    if run:
        save_run(run)


def main() -> None:
    osii_root = Path(os.getenv("OSII_ROOT", "./data_volume/.osii")).resolve()
    configure_job_store(osii_root)
    idle_seconds = max(0.2, float(os.getenv("OSII_WORKER_POLL_SECONDS", "1")))
    while True:
        job = claim_next_queue_job()
        if job is None:
            time.sleep(idle_seconds)
            continue
        try:
            execute_job(job)
            run = get_run(job["run_id"])
            if run and run.get("control_state") == "cancel_requested":
                run["status"] = "cancelled"
                run["control_state"] = "cancelled"
                run["finished_at"] = datetime.now(UTC).isoformat()
                for item in run.get("items", []):
                    if item.get("status") in {"pending", "running"}:
                        item["status"] = "cancelled"
                save_run(run)
                cancel_queue_job(job["id"])
            elif run and run.get("control_state") == "pause_requested":
                run["status"] = "paused"
                run["control_state"] = "paused"
                save_run(run)
                pause_queue_job(job["id"])
            elif run and run.get("status") == "paused":
                pause_queue_job(job["id"])
            elif run and run.get("status") == "cancelled":
                cancel_queue_job(job["id"])
            else:
                complete_queue_job(job["id"])
        except Exception as exc:
            complete_queue_job(job["id"], error=str(exc))


if __name__ == "__main__":
    main()
