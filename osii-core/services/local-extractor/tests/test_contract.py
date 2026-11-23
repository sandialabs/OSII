import base64
from fastapi.testclient import TestClient
from osii_local_extractor.main import app

client = TestClient(app)


def test_docx_is_closed_before_the_reader_reopens_it():
    from io import BytesIO
    from zipfile import ZipFile
    data = BytesIO()
    with ZipFile(data, "w") as package:
        package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Portable DOCX evidence</w:t></w:r></w:p></w:body></w:document>')
    response = client.post("/v1/extract", json={"request_id": "docx-windows", "document": {
        "file_id": "docx", "filename": "document.docx", "content_base64": base64.b64encode(data.getvalue()).decode(),
    }})
    assert response.status_code == 200, response.text
    assert "Portable DOCX evidence" in response.json()["segments"][0]["text"]

def test_contract_and_text_extraction():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/v1/descriptor").json()["name"] == "local.native-text"
    assert "/v1/extract" in client.get("/openapi.json").json()["paths"]
    response = client.post("/v1/extract", json={"request_id": "r1", "document": {"file_id": "f1", "filename": "notes.txt", "media_type": "text/plain", "content_base64": base64.b64encode(b"grounded text").decode()}})
    assert response.status_code == 200
    assert response.json()["segments"][0]["source_origin"]["unit_type"] == "chunk"

def test_invalid_payload_is_422():
    assert client.post("/v1/extract", json={}).status_code == 422
