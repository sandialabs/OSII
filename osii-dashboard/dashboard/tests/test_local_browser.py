"""Exercise the production dashboard against a temporary OSII-local library."""

from contextlib import ExitStack, contextmanager
import json
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
import pymupdf
from playwright.sync_api import expect, sync_playwright

from osii.domain.artifacts.products import product_path, publish_product
from osii.domain.storage.objects import update_synthesis_provenance
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
def baseline_processors(library, extra_endpoints=()):
    root, _, env = library
    services = DASHBOARD.parents[1] / "osii-core" / "services"
    endpoints = list(extra_endpoints)
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
        breadcrumbs = page.get_by_role("navigation", name="Breadcrumbs")
        expect(breadcrumbs.get_by_role("link", name="Files")).to_have_attribute("href", "/files")
        expect(breadcrumbs.locator('[aria-current="page"]')).to_have_text(SAMPLE.name)
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
    page.goto("/intake/advanced")
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
        first_run = queue_directory(page, first, ["report.txt"], "Completed")
        second_run = queue_directory(page, second, ["report.txt", "damaged.pdf"], "Completed with issues", last_folder=first)
        assert [item["status"] for item in first_run["items"]] == ["done"]
        assert sorted(item["status"] for item in second_run["items"]) == ["done", "error"]
        first_id, = first_run["indexing_file_ids"]
        second_id, = second_run["indexing_file_ids"]
        assert first_id != second_id

        detail_path = f"/intake/runs/{second_run['id']}"
        log_requests = []
        page.on("request", lambda request: log_requests.append(request.url)
                if request.url.endswith(f"/api/runs/{second_run['id']}/logs") else None)
        page.get_by_role("link", name=re.compile(r"Completed with issues")).click()
        expect(page).to_have_url(re.compile(detail_path + "$"))
        breadcrumbs = page.get_by_role("navigation", name="Breadcrumbs")
        expect(breadcrumbs.get_by_role("link", name="Queue & activity")).to_have_attribute("href", "/intake?tab=activity")
        failures = page.get_by_role("region", name="Failures", exact=True)
        files = page.get_by_role("table", name="Files and processors")
        expect(failures).to_contain_text("damaged.pdf")
        expect(failures).to_contain_text("local.native-text")
        expect(files.get_by_role("row", name=re.compile("report.txt"))).to_contain_text("Read text · Completed · local.native-text")
        expect(files.get_by_role("row", name=re.compile("damaged.pdf"))).to_contain_text("Read text · Failed · local.native-text")
        assert failures.evaluate("(node) => node.compareDocumentPosition(document.querySelector('table')) & Node.DOCUMENT_POSITION_FOLLOWING")
        expect(page.get_by_text("Refresh log", exact=True)).to_have_count(0)
        assert not log_requests

        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        page.get_by_role("button", name="Copy run report", exact=True).click()
        expect(page.get_by_role("status")).to_have_text("Run report copied.")
        report = json.loads(page.evaluate("navigator.clipboard.readText()"))
        assert report["run_id"] == second_run["id"]
        failed_item = next(item for item in report["items"] if item["status"] == "error")
        assert failed_item["diagnostics"][-1]["python"]["executable"]
        assert any("damaged.pdf" in line for line in report["logs"])
        assert not log_requests
        page.get_by_role("button", name="View diagnostics", exact=True).click()
        expect(page.get_by_role("textbox", name="Run report")).to_have_value(re.compile(r"python"))
        page.get_by_role("button", name="Hide diagnostics", exact=True).click()

        page.get_by_text("Run log", exact=True).click()
        expect(page.locator("details").filter(has_text="Run log")).to_contain_text("Extractor 'local.native-text' failed for damaged.pdf")
        assert not log_requests
        expect(page.get_by_role("button", name="Refresh log", exact=True)).to_be_visible()
        page.reload()
        expect(failures).to_be_visible()
        expect(page.get_by_role("button", name="Refresh log", exact=True)).to_have_count(0)
        breadcrumbs.get_by_role("link", name="Queue & activity").click()
        expect(page).to_have_url(re.compile(r"/intake\?tab=activity$"))

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

        update_synthesis_provenance(root / ".osii", first_id, synthesizer_name="openai.synthesizer",
            synthesizer_version="test", config={"document_metadata": {
                "method": "text_llm", "title": {}, "author": {}, "date": {},
                "agency": {"value": "Test Inspection Office"}, "document_type": {"value": "report"},
            }})
        saved = page.request.put(f"/api/objects/{first_id}/metadata", data={"expected_revision": None, "values": {
            "author": "First File Editor", "agency": "Test Inspection Office", "document_type": "Report",
        }})
        assert saved.ok, saved.text()
        metadata = page.request.put(f"/api/objects/{second_id}/metadata", data={"expected_revision": None, "values": {
            "descriptive_title": "Copper joint inspections", "author": "Test Author", "agency": "Test Engineering Office",
            "document_type": "Report",
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
        expect(page.get_by_role("button", name="Reveal topics")).to_have_count(0)
        expect(overview).to_contain_text("Test Author")
        overview.get_by_role("combobox", name=re.compile("Group by")).click()
        page.get_by_role("option", name="Agencies", exact=True).click()
        expect(overview).to_contain_text("Test Engineering Office")
        expect(overview).to_contain_text("Test Inspection Office")
        expect(overview.get_by_text("AI · OpenAI-compatible synthesis", exact=True)).to_be_visible()
        overview.get_by_role("combobox", name=re.compile("Group by")).click()
        page.get_by_role("option", name="Document types", exact=True).click()
        expect(overview.get_by_text("Report", exact=True)).to_have_count(1)
        expect(overview.get_by_text("Edited · 1", exact=True)).to_be_visible()
        expect(overview.get_by_text("AI · OpenAI-compatible synthesis · 1", exact=True)).to_be_visible()

        page.get_by_role("navigation", name="Main navigation").get_by_role("button", name="Toolbox", exact=True).click()
        expect(page).to_have_url(re.compile("/tools$"))
        expect(page.get_by_role("heading", name="Toolbox", exact=True)).to_be_visible()

        (root / "offline").rename(second.parent)
        shutil.copyfile(SAMPLE, second / "damaged.pdf")
        page.goto(detail_path)
        page.get_by_role("button", name="Retry failed files", exact=True).click()
        expect(page.get_by_text("Completed", exact=True).first).to_be_visible(timeout=30_000)
        expect(failures).to_have_count(0, timeout=30_000)
        after_retry = page.request.get("/api/runs/" + second_run["id"]).json()
        good_item = next(item for item in second_run["items"] if item["status"] == "done")
        kept = next(item for item in after_retry["items"] if item["file_id"] == good_item["file_id"])
        assert kept["finished_at"] == good_item["finished_at"]
        assert kept["extraction_variant_id"] == good_item["extraction_variant_id"]


def test_processor_settings_are_saved_on_a_dedicated_page(isolated_library):
    _, _, env = isolated_library
    with baseline_processors(isolated_library), dashboard_page(isolated_library, "processor-details") as page:
        page.goto("/intake/advanced")
        expect(page.get_by_role("combobox", name="Processing flow")).to_be_visible()
        expect(page.get_by_role("spinbutton", name="chunk chars")).to_have_count(0)
        page.get_by_role("link", name="Configure and test flows").click()
        page.get_by_role("button", name=re.compile(r"^Extractors")).click()
        extractor = "Python text-layer PDF and Office extractor"
        page.get_by_role("link", name=re.compile(extractor)).click()
        expect(page.get_by_role("heading", name=extractor, exact=True)).to_be_visible()
        detail_url = page.url
        chunk_size = page.get_by_role("spinbutton", name="chunk chars")
        expect(chunk_size).to_have_value("4000")
        chunk_size.fill("4200")
        page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.get_by_role("alert").get_by_text("Processor settings saved.")).to_be_visible()
        page.reload()
        expect(page).to_have_url(detail_url)
        expect(chunk_size).to_have_value("4200")
        breadcrumbs = page.get_by_role("navigation", name="Breadcrumbs")
        expect(breadcrumbs.locator('[aria-current="page"]')).to_have_text(extractor)
        expect(breadcrumbs.get_by_role("link", name="Setup", exact=True)).to_have_attribute("href", "/admin/processors")
        breadcrumbs.get_by_role("link", name="Processors", exact=True).click()
        expect(page).to_have_url(re.compile(r"/admin/processors#processors-heading$"))
        expect(page.get_by_role("heading", name="Processors", exact=True)).to_be_visible()

        page.get_by_role("button", name="Register a processor service").click()
        native_endpoint = env["OSII_PROCESSORS"].split(",")[0]
        page.get_by_role("textbox", name="Running processor URL").fill(native_endpoint)
        page.get_by_role("button", name="Discover and register").click()
        expect(page).to_have_url(re.compile(r"/admin/processors/registered/local\.native-text$"))
        expect(page.get_by_role("textbox", name="Processor address")).to_have_value(native_endpoint)
        page.get_by_role("button", name="Check health", exact=True).click()
        expect(page.get_by_role("alert").get_by_text("Processor is reachable.")).to_be_visible()


def test_tool_and_collection_wiki_breadcrumbs_follow_stable_routes(isolated_library):
    _, _, env = isolated_library
    with dashboard_page(isolated_library, "breadcrumbs") as page:
        for route, label in [
            ("/search", "Search"),
            ("/chat", "Chat"),
            ("/research", "Create a Report"),
            ("/library-overview", "Analyze Library"),
            ("/tools/collections", "Create Collections"),
            ("/topics", "Explore Topics"),
            ("/tools/ocr", "OCR Workbench"),
            ("/tools/workbench", "Library-wide processing"),
            ("/tools/search-index", "Search index"),
            ("/admin/database", "Database explorer"),
        ]:
            page.goto(route)
            breadcrumbs = page.get_by_role("navigation", name="Breadcrumbs")
            expect(breadcrumbs.get_by_role("link", name="Toolbox")).to_have_attribute("href", "/tools")
            expect(breadcrumbs.locator('[aria-current="page"]')).to_have_text(label)

        breadcrumbs.get_by_role("link", name="Toolbox").click()
        expect(page).to_have_url(re.compile(r"/tools$"))
        expect(page.get_by_role("navigation", name="Breadcrumbs")).to_have_count(0)

        response = page.request.post("/api/collections", data={"name": "Inspection notes"})
        assert response.ok, response.text()
        collection_id = response.json()["collection"]["id"]
        store = Path(env["OSII_ROOT"])
        scope = {"scope_type": "collection", "collection_id": collection_id}
        publish_product(store, product_path(store, scope, "inspection-wiki.json"), {
            "artifact_type": "wiki_markdown", "title": "Inspection wiki",
            "markdown": "Original inspection guidance.", "citations": [],
        })
        collection_url = f"/collections/{collection_id}"
        page.goto(collection_url)
        expect(breadcrumbs.locator('[aria-current="page"]')).to_have_text("Inspection notes")
        page.get_by_role("link", name="Wikis", exact=True).click()
        expect(page).to_have_url(re.compile(collection_url + r"/wikis$"))
        expect(breadcrumbs.get_by_role("link", name="Collections", exact=True)).to_have_attribute("href", "/collections")
        expect(breadcrumbs.get_by_role("link", name="Inspection notes")).to_have_attribute("href", collection_url)
        expect(breadcrumbs.locator('[aria-current="page"]')).to_have_text("Wikis")

        expect(page.get_by_text("Original inspection guidance.", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Edit", exact=True).click()
        page.get_by_role("textbox", name="Wiki Markdown").fill("Updated inspection guidance.")
        page.get_by_role("button", name="Save", exact=True).click()
        expect(page.get_by_text("Updated inspection guidance.", exact=True)).to_be_visible()
        page.reload()
        expect(page.get_by_text("Updated inspection guidance.", exact=True)).to_be_visible()
        expect(page.get_by_role("tab", name="History (2)", exact=True)).to_be_visible()
        breadcrumbs.get_by_role("link", name="Inspection notes").click()
        expect(page).to_have_url(re.compile(collection_url + "$"))
        breadcrumbs.get_by_role("link", name="Collections", exact=True).click()
        expect(page).to_have_url(re.compile(r"/collections$"))


def test_setup_build_index_queues_existing_text_without_reopening_intake(isolated_library):
    root, source, env = isolated_library
    file = source / "inspection.txt"
    file.write_text("Inspection records cover thermal seals and copper joints.")

    with (
        baseline_processors(isolated_library),
        running_process([sys.executable, "-m", "osii.worker"], cwd=root, env=env),
        dashboard_page(isolated_library, "build-index") as page,
    ):
        queue_directory(page, source, [file.name], "Completed")
        file.rename(root / "offline-inspection.txt")
        page.goto("/admin/processors?view=advanced")
        page.get_by_role("button", name=re.compile(r"^6\. Build index")).click()
        expect(page).to_have_url(re.compile(r"/tools/search-index$"))
        expect(page.get_by_role("heading", name="Search index", exact=True)).to_be_visible()
        expect(page.get_by_text("Connect a working semantic embedding model.", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Build index", exact=True)).to_be_disabled()

        # Exercise the UI's semantic readiness gate with synthetic readiness
        # while the isolated worker performs the real rebuild using local hashing.
        def show_semantic_readiness(route):
            response = route.fetch()
            readiness = response.json()
            readiness["defaults"]["embedder"] = "test.semantic"
            readiness["embedders"].append({
                "id": "test.semantic", "available": True, "model": "test-embedding",
                "display_name": "Test semantic embedder", "detail": "Available", "bundled": False,
            })
            route.fulfill(response=response, json=readiness)

        page.route("**/api/intake/readiness", show_semantic_readiness)
        page.reload()
        expect(page.get_by_text("test-embedding", exact=True)).to_be_visible()
        with page.expect_response(lambda response: response.url.endswith("/api/embeddings/build")
                                  and response.request.method == "POST") as queued:
            page.get_by_role("button", name="Build index", exact=True).click()
        assert queued.value.ok, queued.value.text()
        expect(page).to_have_url(re.compile(r"/intake\?tab=activity$"))
        expect(page.get_by_role("tab", name=re.compile(r"^Queue & activity"))).to_have_attribute("aria-selected", "true")
        run_card = page.get_by_role("link", name=re.compile(r"Full index rebuild.*Completed", re.DOTALL))
        expect(run_card).to_be_visible(timeout=30_000)
        run_card.click()
        expect(page.get_by_role("table", name="Files and processors")).to_contain_text(file.name)
        expect(page.get_by_role("table", name="Files and processors")).to_contain_text("Embed · Completed · local.hashing")
        run = page.request.get("/api/runs/" + queued.value.json()["run_id"]).json()
        assert run["operations"] == {"extract": False, "embed": True}
        assert run["indexing_status"] == "done"
        assert run["indexing_progress"]["completed_documents"] == 1

        tool = page.request.post("/api/enrichment-jobs/run", data={
            "enricher_name": "stats_keywords", "scope": {"scope_type": "root"},
        })
        assert tool.ok, tool.text()
        page.goto("/intake/runs/" + tool.json()["run_id"])
        expect(page.get_by_role("region", name="Processors and models")).to_contain_text("stats_keywords")
        expect(page.get_by_role("table", name="Files and processors")).to_contain_text(file.name)


def test_simple_intake_connects_models_before_document_selection(isolated_library):
    root, source, env = isolated_library
    text = source / "inspection.txt"
    text.write_text("Inspection records cover thermal seals and copper joints.")
    damaged = source / "damaged.pdf"
    damaged.write_bytes(b"%PDF-1.7\nThis is an intentionally invalid PDF fixture.\n")
    unknown = source / "sensor-export.bin"
    unknown.write_bytes(b"\x00\x01\x02\xff")
    image = source / "inspection.png"
    with pymupdf.open() as document:
        page_image = document.new_page(width=600, height=175)
        page_image.insert_text((35, 95), "Inspection records", fontsize=28)
        page_image.get_pixmap(dpi=150).save(image)
    model_port, bridge_port = available_port(), available_port()
    endpoint = f"http://127.0.0.1:{model_port}/v1"
    bridge = f"http://127.0.0.1:{bridge_port}"
    env.update(OSII_MODEL_BRIDGE_URL=bridge, OSII_MODEL_BRIDGE_PORT=str(bridge_port),
               OSII_ENV_FILE=str(root / "secrets.env"), OSII_ALLOW_LOCAL_CONFIG_WRITES="true")
    (root / "fixture_models.py").write_text(r"""
from fastapi import FastAPI, HTTPException, Request
app = FastAPI()
calls = []

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/calls")
def counts():
    return calls

@app.get("/v1/models")
def models():
    return {"data": [{"id": "fixture-writing"}, {"id": "fixture-vectors"}, {"id": "fixture-broken"}]}

@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    calls.append(("embedding", body["model"]))
    if body["model"] != "fixture-vectors":
        raise HTTPException(400, "This model cannot embed")
    return {"model": body["model"], "data": [{"index": i, "embedding": [1.0, 0.5, 0.25]} for i, _ in enumerate(body["input"])]}

@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    calls.append(("chat", body["model"]))
    if body["model"] != "fixture-writing":
        raise HTTPException(400, "This model cannot generate text")
    prompt = str(body["messages"])
    if "document_type" in prompt:
        content = '{"descriptive_title":{"value":"Inspection records"},"title":{},"author":{},"date":{},"agency":{},"document_type":{}}'
    else:
        content = "# Inspection records\nThese documents cover inspections."
    return {"choices": [{"message": {"content": content}}]}
""")
    services = DASHBOARD.parents[1] / "osii-core" / "services"
    ocr_port = available_port()
    ocr_url = f"http://127.0.0.1:{ocr_port}"
    (root / "fixture_ocr.py").write_text(f"""
import shutil
import sys
sys.path.insert(0, {str(services / 'local-tesseract')!r})
from app import main
app = main.app

if shutil.which("tesseract") is None:
    def ocr_fixture(*args, **kwargs):
        return {{"text": "Inspection records", "regions": [], "page_width": 600, "page_height": 175}}
    main._ocr_page = ocr_fixture
""")
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(services / "model-provider-bridge"), "--port", str(bridge_port)]
    with (
        running_server([sys.executable, "-m", "uvicorn", "fixture_ocr:app", "--port", str(ocr_port)],
                       url=ocr_url + "/health", cwd=root, env=env),
        baseline_processors(isolated_library, [ocr_url]),
        running_server([sys.executable, "-m", "uvicorn", "fixture_models:app", "--port", str(model_port)],
                       url=f"http://127.0.0.1:{model_port}/health", cwd=root, env=env),
        running_server(command, url=bridge + "/health", cwd=root, env=env),
        running_process([sys.executable, "-m", "osii.worker"], cwd=root, env=env),
        dashboard_page(isolated_library, "quick-intake") as page,
    ):
        page.goto("/intake")
        expect(page.get_by_role("button", name="Intake & Setup", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Setup", exact=True)).to_have_count(0)
        expect(page.get_by_role("heading", name="1. Connect models", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Browse files", exact=True)).to_have_count(0)
        blocked = page.request.post("/api/runs", data={"processing_flow_id": "quick-start", "queue_paths": [str(text)]})
        assert blocked.status == 409, blocked.text()

        page.get_by_role("button", name="Advanced", exact=True).click()
        page.get_by_role("menuitem", name="Advanced intake", exact=True).click()
        page.get_by_role("button", name="Browse files", exact=True).click()
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_role("list", name="Locations", exact=True)).to_be_visible()
        expect(dialog.get_by_role("navigation", name="Folder breadcrumbs")).to_have_count(0)
        dialog.get_by_role("textbox", name="Folder path", exact=True).fill(str(source))
        dialog.get_by_role("button", name="Go", exact=True).click()
        expect(dialog.get_by_role("list", name="Locations", exact=True)).to_have_count(0)
        expect(dialog.get_by_role("button", name="Parent folder", exact=True)).to_be_enabled()
        dialog.get_by_text(text.name, exact=True).click()
        dialog.get_by_text(damaged.name, exact=True).click()
        dialog.get_by_text(unknown.name, exact=True).click()
        dialog.get_by_text(image.name, exact=True).click()
        dialog.get_by_role("button", name="Use 4 files", exact=True).click()
        page.get_by_role("navigation", name="Breadcrumbs").get_by_role("link", name="Intake & Setup").click()

        page.get_by_role("button", name="Connect embedding model", exact=True).click()
        connect = page.get_by_role("dialog", name="Connect embedding model")
        connect.get_by_role("textbox", name="Endpoint URL").fill(endpoint)
        connect.get_by_label("API key").fill("fixture-key-original")
        connect.get_by_role("button", name="Find models", exact=True).click()
        connect.get_by_role("combobox", name="Embedding model", exact=True).click()
        page.get_by_role("option", name="fixture-vectors", exact=True).click()
        connect.get_by_role("button", name="Save and test", exact=True).click()
        expect(connect).to_have_count(0)
        expect(page.get_by_role("button", name="Browse files", exact=True)).to_have_count(0)

        page.get_by_role("button", name="Connect language model", exact=True).click()
        connect = page.get_by_role("dialog", name="Connect language model")
        connect.get_by_role("combobox", name="Connection", exact=True).click()
        page.get_by_role("option", name=endpoint).click()
        connect.get_by_role("button", name="Find models", exact=True).click()
        connect.get_by_role("combobox", name="Language model", exact=True).click()
        page.get_by_role("option", name="fixture-broken", exact=True).click()
        connect.get_by_role("button", name="Save and test", exact=True).click()
        expect(connect.get_by_role("alert")).to_contain_text("400")
        expect(page.get_by_role("button", name="Browse files", exact=True)).to_have_count(0)
        connect.get_by_role("combobox", name="Language model").click()
        page.get_by_role("option", name="fixture-writing", exact=True).click()
        connect.get_by_role("button", name="Save and test", exact=True).click()
        expect(connect).to_have_count(0)

        process = page.get_by_role("button", name="Process 4 files", exact=True)
        expect(process).to_be_enabled()
        calls_url = f"http://127.0.0.1:{model_port}/calls"
        calls = page.request.get(calls_url).json()
        page.reload()
        expect(process).to_be_enabled()
        assert page.request.get(calls_url).json() == calls

        with page.expect_response(lambda response: response.url.endswith("/api/runs")
                                  and response.request.method == "POST") as queued:
            process.click()
        assert queued.value.ok, queued.value.text()
        id = queued.value.json()["id"]
        expect(page).to_have_url(re.compile(f"/intake/runs/{id}$"))
        run_header = page.get_by_role("heading", level=1).locator("..")
        page.get_by_text("Run log", exact=True).click()
        log = page.locator("details").filter(has_text="Run log")
        expect(run_header.get_by_text("Completed with issues", exact=True)).to_be_visible(timeout=30_000)
        expect(log).to_contain_text("Extractor 'local.native-text' failed for damaged.pdf")
        expect(log).to_contain_text("No built-in reader for .bin")
        run = page.request.get("/api/runs/" + id).json()
        assert run["processing_flow"]["id"] == "quick-start"
        assert run["indexing_status"] == "done"
        good = next(item for item in run["items"] if item["status"] == "done")
        assert good["steps"]["synthesizer"] == "done"
        ocr = next(item for item in run["items"] if item["display"].endswith(image.name))
        assert ocr["status"] == "done" and ocr["extractor"] == "local.tesseract-page-ocr"
        assert ocr["file_id"] in run["indexing_file_ids"]
        ocr_text = Path(env["OSII_ROOT"]) / "objects" / ocr["file_id"] / "text.txt"
        assert "Inspection records" in ocr_text.read_text(encoding="utf-8")
        metadata = next(item for item in run["items"] if item["status"] == "metadata_only")
        assert metadata["file_id"] not in run["indexing_file_ids"]
        expect(page.get_by_role("row", name=re.compile(unknown.name))).to_contain_text("Added without text")
        bundle = Path(env["OSII_ROOT"]) / "objects" / metadata["file_id"]
        assert (bundle / "meta.toml").is_file() and not (bundle / "text.txt").exists()
        catalog = page.request.get("/api/catalog/files?status=metadata_only").json()
        assert any(item["file_id"] == metadata["file_id"] for item in catalog["items"])
        shutil.copyfile(SAMPLE, damaged)
        page.get_by_role("button", name="Retry failed files", exact=True).click()
        expect(page.get_by_role("button", name="Retry failed files", exact=True)).to_have_count(0)
        expect(page.get_by_role("heading", name="Failures", exact=True)).to_have_count(0, timeout=30_000)
        expect(run_header.get_by_text("Completed", exact=True)).to_be_visible(timeout=30_000)
        rerun = page.request.get("/api/runs/" + id).json()
        assert sorted(item["status"] for item in rerun["items"]) == ["done", "done", "done", "metadata_only"]
        assert rerun["completed"] == 4
        assert next(item for item in rerun["items"] if item["file_id"] == good["file_id"])["finished_at"] == good["finished_at"]
        assert next(item for item in rerun["items"] if item["file_id"] == metadata["file_id"])["finished_at"] == metadata["finished_at"]

        secret = root / "secrets.env"
        secret.write_text(secret.read_text().replace("fixture-key-original", "fixture-key-replaced"))
        page.goto("/intake")
        expect(page.get_by_role("button", name="Browse files", exact=True)).to_have_count(0)
        assert not page.request.get("/api/intake/quick-start").json()["ready"]
