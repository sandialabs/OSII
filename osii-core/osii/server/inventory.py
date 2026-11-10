"""Hosted scan coordination over the shared metadata-only filesystem reader."""

from __future__ import annotations
import multiprocessing
import queue
import time
from osii.domain.processing.directory_scan import reader, stop_reader, InterruptedRun
from osii.persistence.inventory import PostgresInventory


def execute_scan(store, settings, job, worker, stopping, report):
    inventory = PostgresInventory(store, settings.source_root)
    scan, source = inventory.scan_context(job, worker)
    context = multiprocessing.get_context("spawn")
    active = {}
    timeouts = 0
    error = None
    try:
        while not stopping.is_set():
            state = store.job(job["id"])["status"]
            if state != "running":
                break
            while len(active) < job["payload"].get("readers", 2):
                path = inventory.claim_directory(scan, job, worker)
                if path is None:
                    break
                output = context.Queue(maxsize=2)
                process = context.Process(
                    target=reader,
                    args=(source, path, job["payload"], output),
                    daemon=True,
                )
                process.start()
                active[path] = [process, output, time.monotonic()]
            if not active:
                break
            for path, task in list(active.items()):
                process, output, last = task
                try:
                    message = output.get(timeout=0.05)
                except queue.Empty:
                    if time.monotonic() - last > job["payload"].get(
                        "timeout_seconds", 30
                    ):
                        message = (
                            "error",
                            "Directory reader timed out; reconnect the share and resume",
                            None,
                        )
                        timeouts += 1
                    elif not process.is_alive():
                        message = (
                            "error",
                            "Directory reader exited before completion; resume to retry",
                            None,
                        )
                    else:
                        continue
                task[2] = time.monotonic()
                if message[0] == "batch":
                    inventory.write_batch(scan, job, worker, message[1], message[2])
                else:
                    inventory.finish_directory(scan, job, worker, path, message)
                    reaped = stop_reader(process, output)
                    del active[path]
                    if not reaped:
                        raise ValueError(
                            "A filesystem reader remains blocked; restore the mount before resuming"
                        )
                if timeouts >= job["payload"].get("readers", 2):
                    raise ValueError(
                        "Source circuit breaker opened after repeated reader timeouts; reconnect and resume"
                    )
    except InterruptedRun:
        pass
    except ValueError as exc:
        error = str(exc)
    finally:
        for process, channel, _ in active.values():
            stop_reader(process, channel)
    failed, pending = inventory.finish_scan(scan, job, worker, error)
    report(
        "Inventory scan stopped with incomplete coverage."
        if failed
        else "Inventory scan checkpoint saved."
        if pending
        else "Inventory scan complete. No contents were read."
    )
    return failed, pending
