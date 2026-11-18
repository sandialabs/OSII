"""Native-library smoke test executed by the frozen executable, without pytest."""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import tempfile
from zipfile import ZipFile


def run() -> dict:
    import faiss
    import numpy as np
    import pymupdf
    from osii.processor_sdk import DocumentInput, ExtractionRequest
    from osii_local_extractor.main import LocalNativeTextExtractor
    from osii_local_tesseract.main import LocalTesseractPageExtractor, SUPPORTED_LANGUAGES

    def request(name: str, content: bytes) -> ExtractionRequest:
        return ExtractionRequest(request_id="packaged-smoke", document=DocumentInput(
            file_id="smoke", filename=name, content_base64=base64.b64encode(content).decode(),
        ))

    extractor = LocalNativeTextExtractor()
    phrase = "Portable evidence survives restart"
    pdf = pymupdf.open()
    page = pdf.new_page(width=900, height=300)
    page.insert_text((30, 120), phrase, fontsize=36)
    extracted = extractor.extract(request("evidence.pdf", pdf.tobytes()))
    assert phrase in extracted.segments[0].text

    docx = BytesIO()
    with ZipFile(docx, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + phrase + '</w:t></w:r></w:p></w:body></w:document>')
    assert phrase in extractor.extract(request("evidence.docx", docx.getvalue())).segments[0].text
    for extension, member in (("pptx", "ppt/slides/slide1.xml"), ("xlsx", "xl/sharedStrings.xml")):
        content = BytesIO()
        with ZipFile(content, "w") as archive:
            archive.writestr(member, "<root><text>" + phrase + "</text></root>")
        assert phrase in extractor.extract(request("evidence." + extension, content.getvalue())).segments[0].text
    for extension in ("txt", "csv", "tsv"):
        assert phrase in extractor.extract(request("evidence." + extension, phrase.encode())).segments[0].text

    image = page.get_pixmap(dpi=180).tobytes("png")
    scanned = pymupdf.open()
    scanned.new_page(width=900, height=300).insert_image(page.rect, stream=image)
    ocr = LocalTesseractPageExtractor()
    for name, content in (("scan.pdf", scanned.tobytes()), ("scan.png", image)):
        response = ocr.extract(request(name, content))
        assert "Portable evidence" in response.segments[0].text, "Bundled OCR could not read the fixture"
    import os
    import subprocess
    binary = os.environ["OSII_TESSERACT_EXECUTABLE"]
    languages = subprocess.run([binary, "--list-langs"], capture_output=True, text=True, check=True).stdout
    assert all(language in languages.split() for language in SUPPORTED_LANGUAGES), "Missing bundled OCR languages"

    with tempfile.TemporaryDirectory(prefix="osii-native-smoke-") as folder:
        path = Path(folder) / "portable.faiss"
        index = faiss.IndexFlatIP(3)
        vectors = np.array([[1, 0, 0], [0, 1, 0]], dtype="float32")
        index.add(vectors)
        faiss.write_index(index, str(path))
        reopened = faiss.read_index(str(path))
        _, hits = reopened.search(vectors[:1], 1)
        assert int(hits[0, 0]) == 0
    return {"status": "ok", "checks": ["pdf", "docx", "pptx", "xlsx", "text", "csv", "tsv", "ocr-pdf", "ocr-image", "ocr-languages", "faiss-reopen"]}
