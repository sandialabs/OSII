import base64
import io
import json
import tomllib
from pathlib import Path

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from osii_vlm_endpoint import main
from PIL import Image


def image():
    buf = io.BytesIO()
    Image.new("RGBA", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def pdf(pages):
    with pymupdf.open() as document:
        for _ in range(pages):
            document.new_page().insert_text((100, 100), "Example")
        return document.tobytes()


def request(raw=None, filename="scan.png"):
    return {
        "request_id": "test",
        "document": {
            "filename": filename,
            "content_base64": base64.b64encode(
                image() if raw is None else raw
            ).decode(),
        },
    }


@pytest.fixture(autouse=True)
def endpoint(monkeypatch):
    monkeypatch.setenv("OSII_VLM_BASE_URL", "https://vision.example.test/v1")
    monkeypatch.setenv("OSII_VLM_MODEL", "vision-model")
    monkeypatch.setenv("OSII_VLM_API_KEY", "unit-test-key")


def test_descriptor_and_readiness():
    manifest = tomllib.loads(
        (Path(__file__).parents[1] / "processor-module.toml").read_text()
    )["processors"][0]
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        descriptor = client.get("/v1/descriptor").json()
        assert client.get("/ready").json() == {
            "status": "ok",
            "model": "vision-model",
            "upstream_checked": False,
        }
    assert descriptor["name"] == manifest["processor_id"]
    assert (
        descriptor["capabilities"]["file_extensions"]
        == manifest["capabilities"]["file_extensions"]
    )
    assert manifest["enabled_by_default"] is False


@pytest.mark.parametrize(
    ("source", "pages"), [(request(), 1), (request(pdf(2), "scan.pdf"), 2)]
)
def test_sends_only_rendered_images_and_returns_page_provenance(source, pages):
    calls = []

    def upstream(req):
        calls.append(req)
        assert str(req.url) == "https://vision.example.test/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer unit-test-key"
        payload = json.loads(req.content)
        assert payload["model"] == "vision-model"
        image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
        assert image_url.startswith("data:image/jpeg;base64,")
        with Image.open(
            io.BytesIO(base64.b64decode(image_url.split(",", 1)[1]))
        ) as rendered:
            assert max(rendered.size) <= main.MAX_EDGE
        return httpx.Response(
            200,
            json={
                "model": "backend-model-v2",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": f"Page {len(calls)} transcription"},
                    },
                ],
            },
        )

    with TestClient(
        main.create_processor_app(main.VisionExtractor(httpx.MockTransport(upstream)))
    ) as client:
        response = client.post("/v1/extract", json=source)
    assert response.status_code == 200, response.text
    assert len(calls) == pages
    segments = response.json()["segments"]
    assert [row["source_origin"]["page"] for row in segments] == list(
        range(1, pages + 1)
    )
    assert segments[0]["source_origin"]["model"] == "backend-model-v2"
    assert "bbox" not in segments[0]["source_origin"]
    assert "unit-test-key" not in response.text


@pytest.mark.parametrize(
    ("source", "status"),
    [
        (request(pdf(11), "large.pdf"), 413),
        (request(b"invalid document", "scan.pdf"), 422),
        (request(b"invalid image"), 422),
        (request(filename="file.wav"), 415),
        ({**request(), "config": {"base_url": "https://unused.example.test"}}, 422),
    ],
)
def test_invalid_source_and_request_overrides_do_not_reach_upstream(source, status):
    def unexpected(_):
        pytest.fail("Invalid intake must not call the upstream.")

    with TestClient(
        main.create_processor_app(main.VisionExtractor(httpx.MockTransport(unexpected)))
    ) as client:
        assert client.post("/v1/extract", json=source).status_code == status


@pytest.mark.parametrize(
    ("upstream", "status"),
    [
        (httpx.Response(401, text="unit-test-key"), 502),
        (httpx.Response(302, headers={"Location": "https://other.example.test"}), 502),
        (httpx.Response(200, json={"choices": []}), 502),
        (
            httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "length", "message": {"content": "partial"}}
                    ]
                },
            ),
            502,
        ),
        (
            httpx.Response(
                200, json={"choices": [{"message": {"content": "[NO_TEXT]"}}]}
            ),
            422,
        ),
    ],
)
def test_sanitizes_errors_and_rejects_partial_results(upstream, status):
    calls = []

    def reply(req):
        calls.append(req)
        return upstream

    with TestClient(
        main.create_processor_app(main.VisionExtractor(httpx.MockTransport(reply)))
    ) as client:
        response = client.post("/v1/extract", json=request())
    assert response.status_code == status, response.text
    assert len(calls) == 1
    assert "unit-test-key" not in response.text


def test_missing_configuration_and_plaintext_remote_credentials(monkeypatch):
    with TestClient(main.app) as client:
        monkeypatch.delenv("OSII_VLM_MODEL")
        assert client.get("/ready").status_code == 503
        monkeypatch.setenv("OSII_VLM_MODEL", "vision-model")
        monkeypatch.setenv("OSII_VLM_BASE_URL", "http://vision.example.test/v1")
        assert client.get("/ready").status_code == 503
