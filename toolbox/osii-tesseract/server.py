from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ocr_pipeline import process_document

app = FastAPI(title="LiteParse OCR API", version="0.1.0")


@app.post("/ocr")
async def ocr_endpoint(
    file: UploadFile = File(...),
    language: str = Form("en"),
):
    if not file:
        raise HTTPException(status_code=400, detail="Missing file")

    try:
        file_bytes = await file.read()
        if not file_bytes:
            return JSONResponse(status_code=400, content={"error": "Empty file"})

        results = process_document(file_bytes, file.filename or "upload", language)
        return {"results": results}

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})