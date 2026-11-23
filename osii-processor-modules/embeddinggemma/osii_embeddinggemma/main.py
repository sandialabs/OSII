from __future__ import annotations

from hashlib import file_digest
import json
from math import isfinite, sqrt
import os
from pathlib import Path
import secrets
import socket
import subprocess
from threading import Lock
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from fastapi import HTTPException
from osii.processor_sdk import (
    Capability, Embedder, EmbeddingRequest, EmbeddingResponse, EmbeddingVector,
    ProcessorDescriptor, ProcessorKind, create_processor_app,
)

from . import DIMENSIONS, MODEL_ID, PROCESSOR_ID


class LlamaRuntime:
    """Own a private embedding-only llama-server process for this service."""

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._lock = Lock()
        self._opener = build_opener(ProxyHandler({}))
        self._url = ""
        self._key = ""
        self.digest = ""

    @staticmethod
    def files() -> tuple[Path, Path]:
        engine = Path(os.environ.get("OSII_EMBEDDINGGEMMA_ENGINE", "")).expanduser()
        model = Path(os.environ.get("OSII_EMBEDDINGGEMMA_WEIGHTS", "")).expanduser()
        if not (engine.is_absolute() and engine.is_file() and model.is_absolute() and model.is_file()):
            raise HTTPException(503, "EmbeddingGemma needs the llama-server executable and text-only GGUF weights.")
        return engine, model

    def _stop(self):
        if self._process is not None:
            if self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            self._process = None

    def close(self):
        with self._lock:
            self._stop()

    def _start(self):
        if self._process is not None and self._process.poll() is None:
            return
        engine, model = self.files()
        with model.open("rb") as handle:
            self.digest = file_digest(handle, "sha256").hexdigest()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self._key = secrets.token_urlsafe(32)
        self._url = f"http://127.0.0.1:{port}"
        kept = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA"}
        environment = {name: value for name, value in os.environ.items() if name.upper() in kept}
        environment["LLAMA_API_KEY"] = self._key
        threads = str(min(4, os.cpu_count() or 1))
        self._process = subprocess.Popen(
            [str(engine), "--model", str(model), "--host", "127.0.0.1", "--port", str(port),
             "--offline", "--no-webui", "--device", "none", "--n-gpu-layers", "0",
             "--embeddings", "--pooling", "mean", "--alias", MODEL_ID, "--parallel", "1",
             "--ctx-size", "8192", "--batch-size", "8192", "--ubatch-size", "8192",
             "--threads", threads, "--no-warmup"],
            cwd=engine.parent, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and self._process.poll() is None:
            try:
                with self._opener.open(self._url + "/health", timeout=1):
                    if self._process.poll() is None:
                        return
            except OSError:
                time.sleep(0.1)
        self._stop()
        raise HTTPException(503, "The CPU EmbeddingGemma runtime could not load its model.")

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            self._start()
            request = Request(
                self._url + "/v1/embeddings",
                json.dumps({"model": MODEL_ID, "input": texts}).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._key},
            )
            try:
                with self._opener.open(request, timeout=90) as response:
                    rows = json.load(response)["data"]
                by_index = {row["index"]: row["embedding"] for row in rows}
                if len(rows) != len(texts) or by_index.keys() != set(range(len(texts))):
                    raise ValueError("The runtime returned the wrong embedding indices.")
                return [_normalized(by_index[index]) for index in range(len(texts))]
            except (URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
                raise HTTPException(503, "The CPU EmbeddingGemma runtime could not embed the input.") from exc


def _normalized(vector: list[float]) -> list[float]:
    values = vector[:DIMENSIONS]
    if len(vector) != 768 or not all(isfinite(value) for value in values):
        raise ValueError("The runtime returned an invalid EmbeddingGemma vector.")
    norm = sqrt(sum(value * value for value in values))
    if not norm:
        raise ValueError("The runtime returned an empty EmbeddingGemma vector.")
    return [value / norm for value in values]


class EmbeddingGemma(Embedder):
    descriptor = ProcessorDescriptor(
        name=PROCESSOR_ID,
        version="0.1.0",
        display_name="EmbeddingGemma 2 (local CPU)",
        description="Semantic embeddings from Google's text model. Processing stays on this computer.",
        kind=ProcessorKind.EMBEDDER,
        capabilities=Capability(output_kinds=["embedding_vector"], embedding_input_purpose=True),
    )

    def __init__(self, runtime: LlamaRuntime):
        self.runtime = runtime

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        if len(request.inputs) > 128:
            raise ValueError("Submit at most 128 text inputs per request.")
        texts = []
        for item in request.inputs:
            purpose = item.metadata.get("purpose", "document")
            if purpose == "query":
                text = f"task: search result | query: {item.text}"
            elif purpose == "document":
                title = item.metadata.get("title") or "none"
                text = f"title: {title} | text: {item.text}"
            else:
                raise ValueError("Embedding purpose must be query or document.")
            length = len(text.encode("utf-8"))
            if length > 4000:
                raise ValueError("EmbeddingGemma inputs must fit in 4,000 UTF-8 bytes including the prompt.")
            texts.append((text, length))
        vectors = []
        batch: list[str] = []
        batch_bytes = 0
        for text, length in texts:
            if len(batch) == 8 or batch_bytes + length > 8000:
                vectors.extend(self.runtime.embed(batch))
                batch, batch_bytes = [], 0
            batch.append(text)
            batch_bytes += length
        vectors.extend(self.runtime.embed(batch))
        return EmbeddingResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            model=MODEL_ID,
            normalized=True,
            vectors=[
                EmbeddingVector(id=item.id, vector=vector, dimensions=DIMENSIONS)
                for item, vector in zip(request.inputs, vectors, strict=True)
            ],
            metadata={"model_digest": self.runtime.digest, "endpoint_type": "local-cpu", "semantic": True},
        )


runtime = LlamaRuntime()
app = create_processor_app(EmbeddingGemma(runtime))
app.add_event_handler("shutdown", runtime.close)


@app.get("/ready")
def ready() -> dict[str, str]:
    runtime.files()
    return {"status": "ok"}
