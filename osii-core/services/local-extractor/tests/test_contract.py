import base64
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_contract_and_text_extraction():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/v1/descriptor").json()["name"] == "local.native-text"
    assert "/v1/extract" in client.get("/openapi.json").json()["paths"]
    response = client.post("/v1/extract", json={"request_id": "r1", "document": {"file_id": "f1", "filename": "notes.txt", "media_type": "text/plain", "content_base64": base64.b64encode(b"grounded text").decode()}})
    assert response.status_code == 200
    assert response.json()["segments"][0]["source_origin"]["unit_type"] == "chunk"

def test_invalid_payload_is_422():
    assert client.post("/v1/extract", json={}).status_code == 422


def test_pdf_extraction_records_embedded_title_and_author():
    import pymupdf

    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Native text")
        pdf.set_metadata({"title": "Recorded title", "author": "Recorded author"})
        content = pdf.tobytes()
    response = client.post("/v1/extract", json={
        "request_id": "pdf-properties",
        "document": {"file_id": "metadata-pdf", "filename": "notes.pdf", "media_type": "application/pdf",
                     "content_base64": base64.b64encode(content).decode()},
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["segments"][0]["text"] == "Native text"
    assert result["document_metadata"]["file_properties"] == {
        "title": "Recorded title", "author": "Recorded author",
    }


def test_office_extraction_records_only_embedded_title_and_author():
    from io import BytesIO
    from zipfile import ZipFile

    content = BytesIO()
    with ZipFile(content, "w") as package:
        package.writestr("word/document.xml", """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:body><w:p><w:r><w:t>Native Word text</w:t></w:r></w:p></w:body>
            </w:document>
        """)
        package.writestr("docProps/core.xml", """
            <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                                xmlns:dc="http://purl.org/dc/elements/1.1/">
                <dc:title>Word title</dc:title><dc:creator>Word author</dc:creator><dc:subject>Subject</dc:subject>
            </cp:coreProperties>
        """)
    response = client.post("/v1/extract", json={
        "request_id": "office-properties",
        "document": {"file_id": "metadata-docx", "filename": "notes.docx",
                     "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     "content_base64": base64.b64encode(content.getvalue()).decode()},
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["segments"][0]["text"] == "Native Word text"
    assert result["document_metadata"]["file_properties"] == {"title": "Word title", "author": "Word author"}
