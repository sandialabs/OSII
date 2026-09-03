"""Default parameter loading helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.models import DetectionParams, RecognitionParams

DEFAULTS_PATH = Path(__file__).parent.parent / "config" / "default_params.json"


def load_default_params() -> dict:
    """Load default detection and recognition parameters from JSON.

    Returns
    -------
    dict
        Dictionary with ``detection`` and ``recognition`` keys.
    """
    fallback = {
        "detection": DetectionParams().model_dump(),
        "recognition": RecognitionParams(confidence_threshold=0.5).model_dump(),
    }

    if not DEFAULTS_PATH.exists():
        return fallback

    try:
        data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return fallback

    detection = DetectionParams(**data.get("detection", {})).model_dump()
    recognition = RecognitionParams(
        **data.get("recognition", {"confidence_threshold": 0.5})
    ).model_dump()

    return {
        "detection": detection,
        "recognition": recognition,
    }


DEFAULT_PARAMS = load_default_params()