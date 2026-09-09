from pathlib import Path
import tomllib

import requests
import tomli_w
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["extractors"])


def extractors_config_path() -> Path:
    return Path("config/extractors.toml").resolve()


def load_extractors_file() -> dict:
    path = extractors_config_path()
    if not path.exists():
        return {"extractors": []}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def validate_extractors(payload: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    extractors = payload.get("extractors")

    if not isinstance(extractors, list):
        return ["'extractors' must be a list."], []

    seen_ids = set()
    allowed_auth_types = {"none", "api_key"}
    allowed_types = {"http"}

    for i, extractor in enumerate(extractors):
        if not isinstance(extractor, dict):
            errors.append(f"extractor {i + 1} must be an object.")
            continue

        extractor_id = extractor.get("id")
        display_name = extractor.get("display_name")
        extractor_type = extractor.get("type")
        auth_type = extractor.get("auth_type")
        enabled = extractor.get("enabled")
        base_url = extractor.get("base_url", "")

        if not extractor_id:
            errors.append(f"extractor {i + 1} missing 'id'.")
        elif extractor_id in seen_ids:
            errors.append(f"Duplicate extractor id: '{extractor_id}'.")
        else:
            seen_ids.add(extractor_id)

        if not display_name:
            errors.append(f"extractor {i + 1} missing 'display_name'.")

        if extractor_type not in allowed_types:
            errors.append(
                f"extractor '{extractor_id or i + 1}' has invalid type '{extractor_type}'. "
                f"Allowed: {sorted(allowed_types)}"
            )

        if auth_type not in allowed_auth_types:
            errors.append(
                f"extractor '{extractor_id or i + 1}' has invalid auth_type '{auth_type}'. "
                f"Allowed: {sorted(allowed_auth_types)}"
            )

        if not isinstance(enabled, bool):
            errors.append(f"extractor '{extractor_id or i + 1}' must have boolean 'enabled'.")

        if extractor_type == "http" and enabled and not base_url:
            warnings.append(f"extractor '{extractor_id}' is enabled but has no base_url configured.")


    return errors, warnings


def healthcheck_extractor(extractor: dict) -> dict:
    extractor_id = extractor.get("id", "")
    extractor_type = extractor.get("type", "")
    enabled = extractor.get("enabled", False)
    base_url = (extractor.get("base_url") or "").strip()
    auth_type = extractor.get("auth_type", "none")

    if not enabled:
        return {
            "id": extractor_id,
            "status": "disabled",
            "ok": False,
            "detail": "extractor is disabled.",
        }

    if extractor_type == "http":
        if not base_url:
            return {
                "id": extractor_id,
                "status": "misconfigured",
                "ok": False,
                "detail": "Enabled HTTP extractor has no base_url.",
            }

        try:
            response = requests.get(base_url, timeout=5)
            return {
                "id": extractor_id,
                "status": "ok" if response.status_code < 500 else "error",
                "ok": response.status_code < 500,
                "detail": f"HTTP {response.status_code}",
            }
        except Exception as exc:
            return {
                "id": extractor_id,
                "status": "unreachable",
                "ok": False,
                "detail": str(exc),
            }

    return {
        "id": extractor_id,
        "status": "unknown",
        "ok": False,
        "detail": f"Unknown extractor type '{extractor_type}'.",
    }


@router.get("/extractors")
async def get_extractors():
    return load_extractors_file()


@router.put("/extractors")
async def put_extractors(payload: dict):
    errors, warnings = validate_extractors(payload)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    path = extractors_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")

    return {
        "ok": True,
        "message": "extractors updated.",
        "path": str(path),
        "extractors": payload.get("extractors", []),
        "warnings": warnings,
    }


@router.get("/extractors/health")
async def get_extractors_health():
    config = load_extractors_file()
    extractors = config.get("extractors", [])
    results = [healthcheck_extractor(extractor) for extractor in extractors]
    return {"extractors": results}
