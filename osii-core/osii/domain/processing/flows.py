"""Named, snapshot-able processing choices shared by Setup and durable jobs."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import os
import sys
from osii.configuration import load_tools_config, load_models_config
from osii.domain.processing.extractor_selection import active_extractor_routes, default_extractor_routes, load_extractor_routes
from osii.domain.processing.defaults import configured_intake_defaults
from osii.domain.model_provider_config import selected_processor


SAMPLE_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[4]
TEXT_LAYER_SAMPLE = SAMPLE_ROOT / "scripts/demo-data/nist-cloud-computing.pdf"
TEXT_LAYER_SAMPLE_PAGE = 5  # physical PDF page 6: the definition, not its cover
TEXT_LAYER_SAMPLE_ID = "nist-cloud-definition"
OFFLINE_FLOW_ID = "standalone-offline"
SEMANTIC_FLOW_ID = "standalone-semantic"


def default_processing_flow_id():
    if os.getenv("OSII_STANDALONE") == "1":
        return SEMANTIC_FLOW_ID if os.getenv("OSII_DEFAULT_EMBEDDER") else OFFLINE_FLOW_ID
    return "bundled"


def processing_flows(root):
    defaults = configured_intake_defaults()
    common = {"synthesizer_name": defaults.get("synthesizer") or selected_processor("synthesizer", osii_root=root),
              "enricher_name": defaults.get("enricher") or "local.stats-keywords",
              "chunk_size": defaults["chunk_size"], "chunk_overlap": defaults["chunk_overlap"]}
    bundled = default_extractor_routes()
    values = {
        "bundled": {"name": "Default bundled processes", "routes": bundled, **common},
        "advanced-ocr": {"name": "Advanced OCR", "routes": [
            {"name": "ocr-pdf-images", "extensions": [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"],
             "extractor": "toolbox.tesseract-opencv", "fallbacks": ["local.tesseract-page-ocr"]}, *bundled], **common},
    }
    configured = load_extractor_routes()
    if configured != bundled:
        values["configured"] = {"name": "Saved extraction routing", "routes": configured, **common}
    settings = load_tools_config()
    for identifier, value in settings.get("processing_flows", {}).items():
        values[identifier] = {**common, **value, "routes": active_extractor_routes(value.get("routes", bundled))}
    default_flow = default_processing_flow_id()
    if default_flow in {OFFLINE_FLOW_ID, SEMANTIC_FLOW_ID}:
        values[OFFLINE_FLOW_ID] = {
            **common,
            "name": "Text and keywords (offline)",
            "routes": bundled,
            "synthesizer_name": "local.extractive-preview",
            "enricher_name": "local.stats-keywords",
            "build_embeddings": False,
            "editable": False,
        }
    if default_flow == SEMANTIC_FLOW_ID:
        values[SEMANTIC_FLOW_ID] = {
            **values[OFFLINE_FLOW_ID],
            "name": "Text, keywords and semantic search",
            "build_embeddings": True,
        }
    try:
        sample_hash = sha256(TEXT_LAYER_SAMPLE.read_bytes()).hexdigest()
    except OSError:
        sample_hash = "missing"
    result = []
    for identifier, value in values.items():
        fingerprint = sha256(json.dumps({"sample": [TEXT_LAYER_SAMPLE_ID, sample_hash, TEXT_LAYER_SAMPLE_PAGE], "flow": value, "models": load_models_config(root),
            "settings": settings.get("processor_settings", {}), "processors": settings.get("tools", {})}, sort_keys=True).encode()).hexdigest()
        report = settings.get("processing_flow_tests", {}).get(identifier)
        result.append({"id": identifier, **deepcopy(value), "fingerprint": fingerprint,
                       "test": report if report and report.get("fingerprint") == fingerprint else None})
    return result


def get_flow(root, identifier):
    return next((flow for flow in processing_flows(root) if flow["id"] == identifier), None)


def flow_payload(flow):
    return {"run_extraction": True, "synthesizer_name": flow["synthesizer_name"],
            "enricher_name": flow["enricher_name"], "build_embeddings": flow.get("build_embeddings", True),
            "chunk_size": flow["chunk_size"], "chunk_overlap": flow["chunk_overlap"],
            "processing_flow": deepcopy(flow)}
