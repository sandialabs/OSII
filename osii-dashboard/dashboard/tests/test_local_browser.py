"""Exercise the production dashboard against a temporary OSII-local library."""

from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright

from osii.extraction.native_text_extractor import NativeTextExtractor


DASHBOARD = Path(__file__).resolve().parents[1]
SAMPLE = DASHBOARD.parents[1] / "scripts" / "demo-data" / "nist-cloud-computing.pdf"


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def running_process(command, *, cwd, env):
    with subprocess.Popen(command, cwd=cwd, env=env) as process:
        try:
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


@contextmanager
def running_server(command, *, url, cwd, env):
    with running_process(command, cwd=cwd, env=env) as process:
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


@pytest.fixture
def isolated_library(tmp_path):
    root = tmp_path.resolve()
    source = root / "library" / "source"
    source.mkdir(parents=True)
    api_port = available_port()
    env = {
        **{key: value for key, value in os.environ.items()
           if not key.startswith(("OSII_", "OPENAI_", "OLLAMA_", "CHAT_", "EMBEDDING_", "DATABASE_URL"))},
        "OSII_STORAGE_BACKEND": "sidecar",
        "OSII_FILESYSTEM_MODE": "local",
        "OSII_ROOT": str(root / ".osii"),
        "OSII_CONFIG_DIR": str(root / "config"),
        "OSII_INVENTORY_DB": str(root / ".osii" / "state" / "inventory.sqlite3"),
        "SHARED_VOLUME_ROOT": str(source),
        "UPLOAD_ORIGINALS_ROOT": str(root / "uploads"),
        "OSII_API_PORT": str(api_port),
        "OSII_WORKER_POLL_SECONDS": "0.2",
        "CHAT_PROVIDER_CHAIN": "extractive",
    }
    return root, source, env


@contextmanager
def baseline_processors(library):
    root, _, env = library
    services = DASHBOARD.parents[1] / "osii-core" / "services"
    endpoints = []
    with ExitStack() as stack:
        for name in ("local-extractor", "local-synthesizer", "local-enricher", "local-embedder"):
            port = available_port()
            endpoint = f"http://127.0.0.1:{port}"
            command = [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(services / name), "--port", str(port)]
            stack.enter_context(running_server(command, url=endpoint + "/health", cwd=root, env=env))
            endpoints.append(endpoint)
        env.update(OSII_PROCESSORS=",".join(endpoints), OSII_INTAKE_SYNTHESIZER="local.extractive-preview",
                   OSII_DEFAULT_EMBEDDER="local.hashing", EMBEDDING_MODEL="osii-local-hashing-v1")
        yield


@contextmanager
def dashboard_page(library, trace_name):
    root, _, env = library
    api_port = env["OSII_API_PORT"]
    core = [sys.executable, "-m", "uvicorn", "osii.main:app", "--port", str(api_port)]
    with running_server(core, url=f"http://127.0.0.1:{api_port}/health", cwd=root, env=env):
        dashboard_port = available_port()
        base_url = f"http://127.0.0.1:{dashboard_port}"
        vite = DASHBOARD / "node_modules" / "vite" / "bin" / "vite.js"
        preview = ["node", str(vite), "preview", "--host", "127.0.0.1", "--port", str(dashboard_port), "--strictPort"]
        with running_server(preview, url=base_url, cwd=DASHBOARD, env=env), sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(base_url=base_url, viewport={"width": 1380, "height": 900})
            context.tracing.start(screenshots=True, snapshots=True)
            try:
                yield context.new_page()
            except Exception:
                context.tracing.stop(path=DASHBOARD / ".cache" / "browser" / f"{trace_name}.zip")
                raise
            finally:
                browser.close()


def test_pdf_preview_recovers_after_source_returns(isolated_library):
    root, source_dir, env = isolated_library
    source = source_dir / SAMPLE.name
    shutil.copyfile(SAMPLE, source)
    extraction = NativeTextExtractor().extract(
        source_path=source, data_volume_root=source_dir.parent, osii_store=Path(env["OSII_ROOT"]),
    )
    file_id = extraction["file_id"]
    disconnected = source.rename(root / "unmounted.pdf")

    with dashboard_page(isolated_library, "pdf-preview-trace") as page:
        page.goto(f"/files/{file_id}")
        expect(page.get_by_role("heading", name=SAMPLE.name)).to_be_visible()
        page.get_by_role("button", name="Split view", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Original file unavailable")
        expect(page.get_by_role("alert")).to_contain_text(str(source.resolve()))
        expect(page.get_by_text("ubiquitous, convenient, on-demand network access", exact=False).first).to_be_visible()

        disconnected.rename(source)
        page.get_by_role("button", name="Retry", exact=True).click()
        expect(page.get_by_text("Page 1 of 7", exact=True)).to_be_visible()
        page.wait_for_function(
            "document.querySelector('canvas')?.getContext('2d')?.getImageData(0, 0, 1, 1).data[3] === 255",
        )
        page.get_by_role("button", name="Next", exact=True).click()
        expect(page.get_by_text("Page 2 of 7", exact=True)).to_be_visible()
        page.get_by_role("button", name="Document metadata", exact=True).click()
        expect(page.get_by_role("separator", name="Resize document panes")).to_be_visible()
        expect(page.get_by_text("Page 1 of 7", exact=True)).to_be_visible()
        expect(page.get_by_role("main").get_by_role("link", name="Open OCR Workbench")).to_have_count(0)
        page.get_by_role("button", name="Single view", exact=True).click()
        expect(page.get_by_role("separator", name="Resize document panes")).to_have_count(0)


def queue_directory(page, path, names, status, *, last_folder=None):
    page.goto("/intake")
    clear = page.get_by_role("button", name="Clear selection", exact=True)
    browse = page.get_by_role("button", name="Browse files")
    browse.wait_for()
    if clear.count():
        clear.click()

    def opens(url, folder):
        parts = urlsplit(url)
        return parts.path == "/api/browse/page" and parse_qs(parts.query).get("path") == [str(folder)]

    held = []
    route_pattern = "**/api/browse/page?*"
    if last_folder:
        def delay_last_folder(route):
            if opens(route.request.url, last_folder):
                held.append(route)
            else:
                route.continue_()

        page.route(route_pattern, delay_last_folder)
        with page.expect_request(lambda request: opens(request.url, last_folder)):
            browse.click()
    else:
        browse.click()
    dialog = page.get_by_role("dialog", name="Select files")
    address = dialog.get_by_role("textbox", name="Folder path")
    address.fill(str(path))
    if last_folder:
        # Let the old request finish after the new path has been typed.
        previous, = held
        with page.expect_response(lambda response: opens(response.url, last_folder)):
            previous.continue_()
        page.unroute(route_pattern)
        expect(address).to_have_value(str(path))
    with page.expect_response(lambda response: opens(response.url, path)) as opened:
        dialog.get_by_role("button", name="Go", exact=True).click()
    assert opened.value.ok, opened.value.text()
    for name in names:
        dialog.get_by_text(name, exact=True).click()
    count = len(names)
    noun = "file" if count == 1 else "files"
    dialog.get_by_role("button", name=f"Use {count} {noun}").click()
    with page.expect_response(lambda response: response.url.endswith("/api/runs") and response.request.method == "POST") as queued:
        page.get_by_role("button", name=f"Queue {count} {noun}", exact=True).click()
    assert queued.value.ok, queued.value.text()
    expect(page.get_by_text(status, exact=True)).to_be_visible(timeout=30_000)
    run_response = page.request.get("/api/runs/" + queued.value.json()["id"])
    assert run_response.ok, run_response.text()
    run = run_response.json()
    assert run["indexing_status"] == "done", run.get("indexing_error")
    return run


def test_intake_from_two_locations_is_browsable_even_after_source_goes_offline(isolated_library):
    root, source, env = isolated_library
    first = source / "reports"
    second = root / "another-location" / "reports"
    first.mkdir()
    second.mkdir(parents=True)
    (first / "report.txt").write_text("The first source has inspection notes about thermal seals.")
    (second / "report.txt").write_text("The second source has inspection notes about copper joints.")
    (second / "damaged.pdf").write_bytes(b"%PDF-1.7\nThis is an intentionally invalid PDF fixture.\n")

    with (
        baseline_processors(isolated_library),
        running_process([sys.executable, "-m", "osii.worker"], cwd=root, env=env),
        dashboard_page(isolated_library, "intake-browse-trace") as page,
    ):
        first_run = queue_directory(page, first, ["report.txt"], "done")
        second_run = queue_directory(page, second, ["report.txt", "damaged.pdf"], "Completed with issues", last_folder=first)
        assert [item["status"] for item in first_run["items"]] == ["done"]
        assert sorted(item["status"] for item in second_run["items"]) == ["done", "error"]
        first_id, = first_run["indexing_file_ids"]
        second_id, = second_run["indexing_file_ids"]
        assert first_id != second_id

        page.goto("/browse")
        expect(page.get_by_role("heading", name="Browse")).to_be_visible()
        page.get_by_role("button", name="Open folder source", exact=True).click()
        page.get_by_role("button", name="Open folder reports", exact=True).click()
        expect(page.get_by_role("table", name="Folder contents")).to_contain_text("report.txt")
        page.get_by_role("button", name="Folder details", exact=True).click()
        expect(page.get_by_role("complementary", name="Folder Details")).to_contain_text("source / reports")
        page.get_by_role("button", name="Close folder details").click()
        page.get_by_role("button", name="Open file report.txt").click()
        expect(page).to_have_url(re.compile("/files/" + first_id))

        second.parent.rename(root / "offline")
        page.goto("/browse")
        page.get_by_role("button", name="Open folder Other locations").click()
        for name in second.as_posix().lstrip("/").split("/"):
            page.get_by_role("button", name="Open folder " + name, exact=True).click()
        expect(page.get_by_role("button", name="Open file damaged.pdf")).to_have_count(0)
        page.get_by_role("button", name="Open file report.txt").click()
        expect(page).to_have_url(re.compile("/files/" + second_id))
        expect(page.get_by_text("The second source has inspection notes about copper joints.", exact=False).first).to_be_visible()

        metadata = page.request.put(f"/api/objects/{second_id}/metadata", data={"expected_revision": None, "values": {
            "descriptive_title": "Copper joint inspections", "author": "Test Author", "agency": "Test Engineering Office",
        }})
        assert metadata.ok, metadata.text()
        page.goto("/files")
        page.get_by_role("button", name="Display settings", exact=True).click()
        dialog = page.get_by_role("dialog", name="Display settings")
        dialog.get_by_role("combobox", name=re.compile("Tile label")).click()
        page.get_by_role("option", name="Descriptive title", exact=True).click()
        dialog.get_by_role("button", name="Save defaults").click()
        expect(page.get_by_role("button", name="Open file Copper joint inspections")).to_be_visible()
        expect(page.get_by_role("button", name="Open file report.txt", exact=True)).to_be_visible()

        folder = "external/" + second.as_posix().lstrip("/")
        page.goto("/browse?" + urlencode({"path": folder, "view": "icons"}))
        expect(page.get_by_role("button", name="Open file Copper joint inspections")).to_be_visible()

        page.goto("/library-overview")
        expect(page.get_by_role("region", name="File locations")).to_contain_text(str(second))
        overview = page.get_by_role("region", name="Document metadata", exact=True)
        expect(overview).to_contain_text("Test Author")
        overview.get_by_role("combobox", name=re.compile("Group by")).click()
        page.get_by_role("option", name="Agencies", exact=True).click()
        expect(overview).to_contain_text("Test Engineering Office")

        page.get_by_role("navigation", name="Main navigation").get_by_role("button", name="Toolbox", exact=True).click()
        expect(page).to_have_url(re.compile("/tools$"))
        expect(page.get_by_role("heading", name="Toolbox", exact=True)).to_be_visible()
