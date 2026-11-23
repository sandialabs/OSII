"""Decode a bounded audio stream and transcribe it with a staged Whisper model."""

from __future__ import annotations

import base64
import binascii
import io
import math
import os
import re
from pathlib import Path
from threading import Lock

from fastapi import HTTPException
from osii.processor_sdk import (
    Capability,
    ExtractionRequest,
    ExtractionResponse,
    Extractor,
    ProcessorDescriptor,
    ProcessorKind,
    TextSegment,
    create_processor_app,
)

AUDIO_FORMATS = {
    ".wav": "wav",
    ".mp3": "mp3",
    ".m4a": "mov",
    ".flac": "flac",
    ".ogg": "ogg",
    ".opus": "ogg",
    ".webm": "matroska",
}
SAMPLE_RATE = 16_000
MAX_SECONDS = 10 * 60
MAX_BYTES = 24 * 1024 * 1024
MODEL_FILES = ("model.bin", "config.json", "tokenizer.json")


def model_directory() -> Path:
    configured = os.environ.get("OSII_WHISPER_MODEL_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_dir() and all((path / name).is_file() for name in MODEL_FILES):
            return path
    raise HTTPException(
        503,
        "Set OSII_WHISPER_MODEL_DIR to a staged CTranslate2 Whisper model directory with model.bin, config.json and tokenizer.json.",
    )


def decode_audio(raw: bytes, audio_format: str):
    import av
    import numpy as np

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    samples = np.empty(SAMPLE_RATE * MAX_SECONDS, dtype=np.float32)
    count = 0

    def append(frames) -> None:
        nonlocal count
        for frame in frames:
            end = count + frame.samples
            if end > len(samples):
                raise HTTPException(
                    413, "Audio exceeds 10 minutes. Split the recording and retry."
                )
            samples[count:end] = frame.to_ndarray().ravel()
            count = end

    def deny_external_input(*_args):
        raise OSError("Audio may not open other files or URLs.")

    try:
        with av.open(
            io.BytesIO(raw), format=audio_format, io_open=deny_external_input
        ) as container:
            if not container.streams.audio:
                raise HTTPException(422, "No audio stream was found.")
            for frame in container.decode(audio=0):
                append(resampler.resample(frame))
            append(resampler.resample(None))
    except (av.error.FFmpegError, ValueError):
        raise HTTPException(
            422, "Whisper could not decode the supplied audio."
        ) from None
    if not count:
        raise HTTPException(422, "The audio stream is empty.")
    samples[:count] /= 32768.0
    return samples[:count]


class WhisperExtractor(Extractor):
    descriptor = ProcessorDescriptor(
        name="local.whisper",
        version="0.1.0",
        kind=ProcessorKind.EXTRACTOR,
        display_name="Whisper speech to text",
        description="Transcribes audio locally and keeps start and end times for each segment.",
        capabilities=Capability(
            file_extensions=list(AUDIO_FORMATS), output_kinds=["text"]
        ),
        config_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "language": {
                    "type": "string",
                    "title": "Spoken language code (blank to detect)",
                    "default": "",
                }
            },
        },
    )

    def __init__(self):
        self._busy = Lock()
        self._model_path = None
        self._model = None

    def model(self, path: Path):
        if path == self._model_path:
            return self._model
        from faster_whisper import WhisperModel

        try:
            self._model = WhisperModel(
                str(path), device="cpu", compute_type="int8", local_files_only=True
            )
        except (RuntimeError, OSError, ValueError):
            raise HTTPException(
                503,
                "Whisper could not load the staged model. Check the model files and CPU runtime.",
            ) from None
        self._model_path = path
        return self._model

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        audio_format = AUDIO_FORMATS.get(Path(request.document.filename).suffix.lower())
        if audio_format is None:
            raise HTTPException(
                415, "Choose a WAV, MP3, M4A, FLAC, Ogg, Opus or WebM audio file."
            )
        language = request.config.get("language", "")
        if (
            request.config.keys() - {"language"}
            or not isinstance(language, str)
            or (language and not re.fullmatch(r"[a-z]{2,3}", language))
        ):
            raise HTTPException(
                422,
                "Use a lowercase Whisper language code, such as en, or leave it blank.",
            )
        encoded = request.document.content_base64
        if not encoded:
            raise HTTPException(422, "Supply the audio file bytes as content_base64.")
        if len(encoded) > 4 * ((MAX_BYTES + 2) // 3):
            raise HTTPException(
                413, "Audio exceeds 24 MiB. Split the recording and retry."
            )
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, "Audio bytes must be valid Base64.") from None
        if len(raw) > MAX_BYTES:
            raise HTTPException(
                413, "Audio exceeds 24 MiB. Split the recording and retry."
            )
        if not self._busy.acquire(blocking=False):
            raise HTTPException(
                429,
                "Whisper is transcribing another recording. Retry after it finishes.",
            )
        try:
            path = model_directory()
            audio = decode_audio(raw, audio_format)
            output, info = self.model(path).transcribe(
                audio, language=language or None, beam_size=1
            )
            segments = []
            for item in output:
                text = item.text.strip()
                if (
                    text
                    and math.isfinite(item.start)
                    and math.isfinite(item.end)
                    and 0 <= item.start <= item.end
                ):
                    segments.append(
                        TextSegment(
                            id=f"speech-{len(segments) + 1:05d}",
                            segment_type="text",
                            text=text,
                            source_origin={
                                "start_seconds": item.start,
                                "end_seconds": item.end,
                                "model": path.name,
                            },
                        )
                    )
        except ValueError:
            raise HTTPException(
                422,
                "Whisper could not transcribe the recording with the selected language.",
            ) from None
        except (RuntimeError, OSError):
            raise HTTPException(
                503, "The local Whisper runtime failed during transcription."
            ) from None
        finally:
            self._busy.release()
        if not segments:
            raise HTTPException(
                422, "Whisper returned no speech text for this recording."
            )
        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=segments,
            document_metadata={
                "language": info.language,
                "model": path.name,
                "duration_seconds": len(audio) / SAMPLE_RATE,
            },
        )


app = create_processor_app(WhisperExtractor())


@app.get("/ready")
def ready():
    return {"status": "ok", "model": model_directory().name}
