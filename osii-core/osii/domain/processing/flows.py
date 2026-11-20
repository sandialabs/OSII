"""Named, snapshot-able processing choices shared by Setup and durable jobs."""
from copy import deepcopy
from hashlib import sha256
import json
from osii.configuration import load_tools_config, load_models_config
from osii.domain.processing.extractor_selection import default_extractor_routes, load_extractor_routes
from osii.domain.processing.defaults import configured_intake_defaults
from osii.domain.model_provider_config import selected_processor


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
             "extractor": "toolbox.tesseract-opencv", "fallbacks": ["local.tesseract-page-ocr", "tika"]}, *bundled], **common},
    }
    configured = load_extractor_routes()
    if configured != bundled:
        values["configured"] = {"name": "Saved extraction routing", "routes": configured, **common}
    settings = load_tools_config()
    for identifier, value in settings.get("processing_flows", {}).items():
        values[identifier] = {**common, **value}
    result = []
    for identifier, value in values.items():
        fingerprint = sha256(json.dumps({"flow": value, "models": load_models_config(root),
            "settings": settings.get("processor_settings", {}), "processors": settings.get("tools", {})}, sort_keys=True).encode()).hexdigest()
        report = settings.get("processing_flow_tests", {}).get(identifier)
        result.append({"id": identifier, **deepcopy(value), "fingerprint": fingerprint,
                       "test": report if report and report.get("fingerprint") == fingerprint else None})
    return result


def get_flow(root, identifier):
    return next((flow for flow in processing_flows(root) if flow["id"] == identifier), None)


def flow_payload(flow):
    return {"run_extraction": True, "synthesizer_name": flow["synthesizer_name"],
            "enricher_name": flow["enricher_name"], "build_embeddings": True,
            "chunk_size": flow["chunk_size"], "chunk_overlap": flow["chunk_overlap"],
            "processing_flow": deepcopy(flow)}
