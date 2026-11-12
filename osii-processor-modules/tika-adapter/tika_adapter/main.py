"""Processor module for managed or external Apache Tika."""
import base64
import os
from contextlib import asynccontextmanager
from .runtime import ManagedTika
from urllib.parse import urlsplit

import requests
from fastapi import HTTPException
from osii.processor_sdk import (Capability, ExtractionRequest, ExtractionResponse,
    Extractor, ProcessorDescriptor, ProcessorKind, TextSegment, create_processor_app)


DEFAULT_ENDPOINT = f"http://127.0.0.1:{os.getenv('OSII_TIKA_SERVER_PORT', '9998')}"

def endpoint(value: str) -> str:
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Apache Tika endpoint must be an HTTP(S) base URL without credentials, query, or fragment.')
    return value


def upstream_error(address: str, error: requests.RequestException) -> str:
    status = error.response.status_code if error.response is not None else None
    reason = f"returned HTTP {status}" if status else "is unavailable"
    return f"Apache Tika {reason} at {address}. Check the server and its endpoint in Setup."


class TikaExtractor(Extractor):
    descriptor = ProcessorDescriptor(
        name='tika', version='2.0.0', display_name='Apache Tika',
        description='Extracts plain text through Apache Tika; no page boxes or OCR are inferred.',
        kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(file_extensions=['*']),
        config_schema={'type': 'object', 'properties': {
            'tika_endpoint': {'type': 'string', 'title': 'Apache Tika endpoint', 'default': DEFAULT_ENDPOINT, 'description': 'Optional external Tika server; leave the default for the managed runtime.'},
            'chunk_chars': {'type': 'integer', 'minimum': 1, 'maximum': 1000000, 'default': 4000},
        }, 'additionalProperties': False},
    )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        address = endpoint(str(request.config.get('tika_endpoint', DEFAULT_ENDPOINT)))
        size = request.config.get('chunk_chars', 4000)
        if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 1000000:
            raise ValueError('chunk_chars must be between 1 and 1000000.')
        if not request.document.content_base64:
            raise ValueError('document.content_base64 is required; this service never opens source paths.')
        try:
            content = base64.b64decode(request.document.content_base64, validate=True)
        except ValueError as exc:
            raise ValueError('Invalid document content_base64.') from exc
        try:
            response = requests.put(address + '/tika', data=content,
                headers={'Accept': 'text/plain', 'Content-Type': request.document.media_type or 'application/octet-stream'}, timeout=300)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f'Apache Tika extraction failed. {upstream_error(address, exc)}') from exc
        text = response.text.strip()
        return ExtractionResponse(request_id=request.request_id, processor=self.descriptor,
            segments=[TextSegment(id=f'chunk-{i // size + 1}', segment_type='chunk', text=text[i:i+size],
                source_origin={'source_type': 'generic_text', 'unit_type': 'chunk', 'chunk_index': i // size + 1,
                               'tika_endpoint': address, 'extracted_char_start': i, 'extracted_char_end': min(i+size, len(text))})
                      for i in range(0, len(text), size)],
            warnings=[] if text else ['No text content extracted.'])


@asynccontextmanager
async def lifespan(app):
    runtime = ManagedTika()
    app.state.tika_runtime = runtime
    runtime.start()
    try:
        yield
    finally:
        runtime.close()


app = create_processor_app(TikaExtractor())
app.router.lifespan_context = lifespan


@app.get('/upstream-health')
def upstream_health(tika_endpoint: str = DEFAULT_ENDPOINT):
    try:
        address = endpoint(tika_endpoint)
        response = requests.get(address + '/version', timeout=3)
        response.raise_for_status()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=upstream_error(address, exc)) from exc
    return {'status': 'ok', 'endpoint': address}
