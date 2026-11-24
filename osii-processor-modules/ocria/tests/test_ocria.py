import base64
import io
import tomllib
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from liteparse.types import ParsedPage, ParseResult
from osii_ocria import main
from PIL import Image


def pdf(pages=1, **size):
    with pymupdf.open() as doc:
        for _ in range(pages):
            doc.new_page(**size).insert_text((72, 72), "OSII OCR test")
        return doc.tobytes()


def png():
    buf = io.BytesIO()
    Image.new("RGBA", (400, 300), "white").save(buf, format="PNG")
    return buf.getvalue()


def payload(filename="scan.pdf", raw=None):
    return {
        "request_id": "scan",
        "document": {
            "filename": filename,
            "content_base64": base64.b64encode(pdf() if raw is None else raw).decode(),
        },
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OSII_OCRIA_LICENSE_ACKNOWLEDGED", "true")
    monkeypatch.setattr(
        main.models,
        "list",
        lambda: [main.models.InstalledModel(main.MODEL, "test-v1", "fixture", 1, True)],
    )
    with TestClient(main.create_processor_app(main.OcriaExtractor())) as client:
        yield client


def test_descriptor_manifest_and_ready(client):
    manifest = tomllib.loads(
        (Path(__file__).parents[1] / "processor-module.toml").read_text()
    )["processors"][0]
    with TestClient(main.app) as app:
        descriptor = app.get("/v1/descriptor").json()
        assert app.get("/health").status_code == 200
        assert app.get("/openapi.json").status_code == 200
        assert app.get("/ready").json() == {
            "status": "ok",
            "model": "OCRia-nano-1",
            "version": "test-v1",
        }
    assert manifest["enabled_by_default"] is False
    assert descriptor["name"] == manifest["processor_id"]
    assert (
        descriptor["capabilities"]["file_extensions"]
        == manifest["capabilities"]["file_extensions"]
    )


@pytest.mark.parametrize(("ack", "complete"), [(False, True), (True, False)])
def test_must_acknowledge_license_and_stage_complete_model(monkeypatch, ack, complete):
    monkeypatch.setenv("OSII_OCRIA_LICENSE_ACKNOWLEDGED", str(ack).lower())
    monkeypatch.setattr(
        main.models,
        "list",
        lambda: [
            main.models.InstalledModel(main.MODEL, "test", "fixture", 1, complete)
        ],
    )

    def unexpected(*args, **kwargs):
        pytest.fail("Unconfigured service must not load or pull the model.")

    monkeypatch.setattr(main.models, "pull", unexpected)
    monkeypatch.setattr(main, "LiteParse", unexpected)
    with TestClient(main.app) as client:
        assert client.get("/ready").status_code == 503
        response = client.post("/v1/extract", json=payload())
    assert response.status_code == 503
    assert ("not staged" if ack else "Model License") in response.text


class StubParser:
    def __init__(self, **options):
        assert options["ocr_backend"] == "ocria-nano"
        assert options["ocr_failure_fatal"]
        assert options["parse_timeout"] == 90

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def parse(self, content):
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            pages = [
                ParsedPage(
                    page.number + 1,
                    page.rect.width,
                    page.rect.height,
                    "Sample",
                    "# Sample",
                    None,
                    [],
                )
                for page in doc
            ]
        return ParseResult(pages, "Sample", len(pages))


@pytest.mark.parametrize(
    ("filename", "raw", "pages"),
    [
        ("scan.pdf", pdf(2), 2),
        ("scan.png", png(), 1),
    ],
)
def test_extracts_page_linked_markdown(client, monkeypatch, filename, raw, pages):
    monkeypatch.setattr(main, "LiteParse", StubParser)
    response = client.post("/v1/extract", json=payload(filename, raw))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["request_id"] == "scan"
    assert result["document_metadata"]["model_package_version"] == "test-v1"
    assert [segment["source_origin"]["page"] for segment in result["segments"]] == list(
        range(1, pages + 1)
    )
    assert result["segments"][0]["text"] == "# Sample"
    assert result["segments"][0]["segment_type"] == "markdown"


@pytest.mark.parametrize(
    ("filename", "raw", "status"),
    [
        ("scan.pdf", pdf(26), 413),
        ("scan.pdf", pdf(width=4000), 413),
        ("scan.pdf", b"not PDF", 422),
        ("scan.png", b"not PNG", 422),
        ("scan.mp3", b"", 415),
    ],
)
def test_rejects_before_starting_runtime(client, monkeypatch, filename, raw, status):
    def unexpected(**_):
        pytest.fail("Invalid input must not start the parser.")

    monkeypatch.setattr(main, "LiteParse", unexpected)
    assert client.post("/v1/extract", json=payload(filename, raw)).status_code == status


def test_incomplete_parse_is_rejected(client, monkeypatch):
    class Partial(StubParser):
        def parse(self, content):
            result = super().parse(content)
            result.pages.pop()
            return result

    monkeypatch.setattr(main, "LiteParse", Partial)
    response = client.post("/v1/extract", json=payload(raw=pdf(2)))
    assert response.status_code == 422
    assert "no partial result" in response.text


def test_pinned_native_parser_interface_without_model(tmp_path, monkeypatch):
    monkeypatch.setenv("LITEPARSE_MODEL_DIR", str(tmp_path))
    with main.LiteParse(
        ocr_enabled=False,
        ocr_backend="tesseract",
        output_format="markdown",
        num_workers=1,
        pool_size=1,
        parse_timeout=15,
    ) as parser:
        result = parser.parse(pdf())
    assert result.pages[0].page_num == 1
    assert "OSII OCR test" in result.pages[0].markdown
