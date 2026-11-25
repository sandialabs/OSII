"""Profile-scoped verification for the standard intake flow."""

from copy import deepcopy
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from threading import RLock
import uuid

from osii.configuration import load_models_config, model_connection, save_models_config
from osii.domain.env_credentials import resolve_env_value, write_env_value
from osii.domain.model_provider_config import selected_model, selected_processor
from osii.domain.processing.defaults import configured_intake_defaults
from osii.domain.processing.extractor_selection import default_extractor_routes
from osii.domain.processing.model_probe import probe_model
from osii.domain.storage.atomic import atomic_write_text
from osii.processor_sdk.diagnostics import redact

FLOW_ID = "quick-start"
ROLES = {"embedding": ("embedding",), "language": ("chat", "synthesis")}
_WRITE_LOCK = RLock()


def _path(root: Path) -> Path:
    return root / "state" / "quick-intake.json"


def _read(root: Path) -> dict:
    try:
        value = json.loads(_path(root).read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("salt"), str) and isinstance(value.get("checks"), dict):
            return value
    except (OSError, ValueError):
        pass
    return {"salt": secrets.token_hex(32), "checks": {}}


def _target(root: Path, capability: str, config: dict) -> dict | None:
    alias = config.get("defaults", {}).get(capability)
    connection = model_connection(alias, root) if alias else None
    if connection and connection.get("enabled", True) and capability in connection.get("capabilities", []):
        model, address = connection.get("model"), connection.get("base_url")
        if model and address and (capability != "embedding" or model != "osii-local-hashing-v1"):
            protocol = "ollama" if connection.get("type") == "ollama-local" else "openai"
            key = "" if protocol == "ollama" else resolve_env_value(connection.get("api_key_env") or "OPENAI_API_KEY")[0]
            return {"alias": alias, "model": model, "endpoint": address, "protocol": protocol, "key": key}
    if capability == "embedding" and not alias:
        address = os.getenv("OSII_BUNDLED_EMBEDDER_URL", "").rstrip("/")
        processor = selected_processor("embedder", osii_root=root)
        if address and processor and processor != "local.hashing":
            return {"alias": processor, "model": selected_model("embedder", osii_root=root),
                    "endpoint": address, "protocol": "bundled", "key": ""}
    return None


def _targets(root: Path, role: str) -> list[dict]:
    config = load_models_config(root)
    result = [_target(root, capability, config) for capability in ROLES[role]]
    return [target for target in result if target] if all(result) else []


def _stamp(targets: list[dict], salt: str) -> str:
    return hmac.new(salt.encode(), json.dumps(targets, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def status(root: Path) -> dict:
    saved = _read(root)
    roles = {}
    for role in ROLES:
        targets = _targets(root, role)
        recorded = saved["checks"].get(role) or {}
        current = bool(targets and recorded.get("stamp") == _stamp(targets, saved["salt"]))
        roles[role] = {
            "state": ("ready" if recorded.get("ok") else "failed") if current else "needs_test" if targets else "needs_connection",
            "models": list(dict.fromkeys(target["model"] for target in targets)),
            "bundled": any(target["protocol"] == "bundled" for target in targets),
            "detail": recorded.get("detail") if current else None,
        }
    return {"ready": all(value["state"] == "ready" for value in roles.values()), **roles}


def _record(root: Path, role: str, targets: list[dict], result: dict) -> None:
    with _WRITE_LOCK:
        if _targets(root, role) != targets:
            raise ValueError("The model settings changed during the check. Try again.")
        saved = _read(root)
        saved["checks"][role] = {
            "stamp": _stamp(targets, saved["salt"]),
            "ok": result["ok"],
            "detail": result.get("detail"),
        }
        atomic_write_text(_path(root), json.dumps(saved))


def check(root: Path, role: str) -> dict:
    targets = _targets(root, role)
    if not targets:
        raise ValueError("Connect a model before checking it.")
    unique = {(target["model"], target["endpoint"], target["protocol"], target["key"]): target for target in targets}
    for target in unique.values():
        if target["protocol"] == "bundled":
            from osii.domain.processing.capability_readiness import embedding_readiness
            readiness = embedding_readiness(root)
            result = {"ok": readiness.get("available", False), "detail": readiness.get("detail")}
        else:
            result = probe_model(target["endpoint"], target["protocol"], target["key"],
                                 target["model"], "embedding" if role == "embedding" else "chat")
        if not result["ok"]:
            break
    _record(root, role, targets, result)
    return status(root)


def check_bundled_at_startup(root: Path) -> None:
    if status(root)["embedding"]["bundled"]:
        try:
            check(root, "embedding")
        except (OSError, ValueError):
            # The app can still show the failed or unverified role and offer a retry.
            pass


def connect(root: Path, role: str, *, model: str, protocol: str, endpoint: str, key: str,
            provider_id: str = "", display_name: str = "") -> dict:
    if role == "embedding" and model == "osii-local-hashing-v1":
        raise ValueError("Choose a semantic embedding model.")
    before = deepcopy(load_models_config(root))
    existing = model_connection(provider_id, root) if provider_id else None
    if provider_id and not existing:
        raise ValueError("The saved connection could not be found.")
    credential = existing.get("api_key_env", "") if existing else ""
    if existing:
        endpoint = existing["base_url"]
        protocol = "ollama" if existing["type"] == "ollama-local" else "openai"
        display_name = existing.get("display_name") or display_name
        key = resolve_env_value(credential or "OPENAI_API_KEY")[0] if protocol == "openai" else ""
        if not credential and key:
            credential = "OPENAI_API_KEY"
    result = probe_model(endpoint, protocol, key, model, "embedding" if role == "embedding" else "chat")
    if not result["ok"]:
        # A new key has not entered the credential store yet.
        error = result.get("detail") or "The model did not pass its test."
        raise ValueError(redact(error.replace(key, "[REDACTED]") if key else error))
    alias = "quick-" + uuid.uuid4().hex[:16]  # keep existing named models and independent defaults
    with _WRITE_LOCK:
        if load_models_config(root) != before:
            raise ValueError("The model settings changed during the test. Try again.")
        if not existing and protocol == "openai":
            credential = "OSII_" + alias.upper().replace("-", "_") + "_API_KEY"
            if key:
                write_env_value(credential, key)
        entry = {
            "type": "ollama-local" if protocol == "ollama" else "openai-compatible",
            "base_url": endpoint, "model": model, "enabled": True,
            "capabilities": list(ROLES[role]), "display_name": display_name,
        }
        if credential:
            entry["api_key_env"] = credential
        before.setdefault("models", {})[alias] = entry
        before.setdefault("defaults", {}).update({capability: alias for capability in ROLES[role]})
        save_models_config(before)
        targets = _targets(root, role)
        if not targets or targets[0]["key"] != key:
            raise ValueError("The credential changed during the test. Check the saved connection.")
        _record(root, role, targets, result)
    return status(root)


def flow(root: Path) -> dict:
    defaults = configured_intake_defaults()
    if not status(root)["ready"]:
        raise ValueError("Test the embedding and language models before processing files in Simple intake.")
    return {
        "id": FLOW_ID, "name": "Standard intake", "routes": default_extractor_routes(),
        "synthesizer_name": selected_processor("synthesizer", osii_root=root),
        "enricher_name": "local.stats-keywords",
        "chunk_size": defaults["chunk_size"], "chunk_overlap": defaults["chunk_overlap"],
    }
