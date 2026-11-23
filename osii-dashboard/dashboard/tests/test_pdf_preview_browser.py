"""Exercise the production dashboard against a temporary OSII-local library."""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

from osii.extraction.native_text_extractor import NativeTextExtractor


DASHBOARD = Path(__file__).resolve().parents[1]
SAMPLE = DASHBOARD.parents[1] / "scripts" / "demo-data" / "nist-cloud-computing.pdf"


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def running_server(command, *, url, cwd, env):
    with subprocess.Popen(command, cwd=cwd, env=env) as process:
        try:
            deadline = time.monotonic() + 30
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    with urlopen(url, timeout=0.5) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"Test server did not start at {url}: {command}")
            yield
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def test_pdf_preview_recovers_after_source_returns(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / SAMPLE.name
    shutil.copyfile(SAMPLE, source)
    store = tmp_path / ".osii"
    extraction = NativeTextExtractor().extract(
        source_path=source, data_volume_root=tmp_path, osii_store=store,
    )
    file_id = extraction["file_id"]
    disconnected = tmp_path / "unmounted.pdf"
    source.rename(disconnected)

    api_port = available_port()
    env = {
        **os.environ,
        "OSII_STORAGE_BACKEND": "sidecar",
        "OSII_FILESYSTEM_MODE": "local",
        "OSII_ROOT": str(store),
        "SHARED_VOLUME_ROOT": str(source_dir),
        "UPLOAD_ORIGINALS_ROOT": str(tmp_path / "uploads"),
        "OSII_API_PORT": str(api_port),
    }
    core = [sys.executable, "-m", "uvicorn", "osii.main:app", "--port", str(api_port)]
    with running_server(core, url=f"http://127.0.0.1:{api_port}/health", cwd=tmp_path, env=env):
        dashboard_port = available_port()
        base_url = f"http://127.0.0.1:{dashboard_port}"
        vite = DASHBOARD / "node_modules" / "vite" / "bin" / "vite.js"
        preview = ["node", str(vite), "preview", "--host", "127.0.0.1", "--port", str(dashboard_port), "--strictPort"]
        with running_server(preview, url=base_url, cwd=DASHBOARD, env=env), sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(base_url=base_url)
            context.tracing.start(screenshots=True, snapshots=True)
            page = context.new_page()
            try:
                page.goto(f"/files/{file_id}")
                expect(page.get_by_role("heading", name=SAMPLE.name)).to_be_visible()
                page.get_by_role("button", name="Source and text").click()
                expect(page.get_by_role("alert")).to_contain_text("Original file unavailable")
                expect(page.get_by_text("ubiquitous, convenient, on-demand network access", exact=False).first).to_be_visible()

                disconnected.rename(source)
                page.get_by_role("button", name="Retry", exact=True).click()
                expect(page.get_by_text("Page 1 of 7", exact=True)).to_be_visible()
                page.wait_for_function(
                    "document.querySelector('canvas')?.getContext('2d')?.getImageData(0, 0, 1, 1).data[3] === 255",
                )
                page.get_by_role("button", name="Next", exact=True).click()
                expect(page.get_by_text("Page 2 of 7", exact=True)).to_be_visible()
            except Exception:
                context.tracing.stop(path=DASHBOARD / ".cache" / "browser" / "pdf-preview-trace.zip")
                raise
            finally:
                browser.close()
