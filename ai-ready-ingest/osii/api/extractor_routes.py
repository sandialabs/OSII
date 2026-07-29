from pathlib import Path
import tomllib

import tomli_w
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["extractor-routes"])


def extractor_routes_path() -> Path:
    return Path("config/extractor_routes.toml").resolve()


def extractors_config_path() -> Path:
    return Path("config/extractors.toml").resolve()


def load_extractor_routes_file() -> dict:
    path = extractor_routes_path()
    if not path.exists():
        return {"routes": []}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_extractors_file() -> dict:
    path = extractors_config_path()
    if not path.exists():
        return {"extractors": []}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def validate_routes(payload: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    routes = payload.get("routes")

    if not isinstance(routes, list):
        return ["'routes' must be a list."], []

    seen_names = set()
    seen_extensions = {}
    catch_all_seen_at = None

    extractors = load_extractors_file().get("extractors", [])
    extractor_map = {p.get("id"): p for p in extractors if p.get("id")}

    for i, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f"Route {i + 1} must be an object.")
            continue

        name = route.get("name")
        extractor = route.get("extractor")
        extensions = route.get("extensions")

        if not name:
            errors.append(f"Route {i + 1} missing 'name'.")
        elif name in seen_names:
            errors.append(f"Duplicate route name: '{name}'.")
        else:
            seen_names.add(name)

        if not extractor:
            errors.append(f"Route {i + 1} missing 'extractor'.")
        else:
            extractor_info = extractor_map.get(extractor)
            if extractor_info is None:
                warnings.append(
                    f"Route '{name or i + 1}' references extractor '{extractor}', "
                    f"which is not present in the extractor registry."
                )
            elif not extractor_info.get("enabled", False):
                warnings.append(
                    f"Route '{name or i + 1}' references extractor '{extractor}', "
                    f"but that extractor is currently disabled."
                )

        if not isinstance(extensions, list) or not extensions:
            errors.append(f"Route {i + 1} must have a non-empty 'extensions' list.")
            continue

        normalized_exts = []
        for ext in extensions:
            if not isinstance(ext, str) or not ext.strip():
                errors.append(f"Route {i + 1} has an invalid extension value.")
                continue

            ext = ext.strip()

            if ext != "*" and not ext.startswith("."):
                errors.append(
                    f"Route '{name or i + 1}' has invalid extension '{ext}'. "
                    f"Extensions must start with '.' or be '*'."
                )

            normalized_exts.append(ext.lower())

        if "*" in normalized_exts:
            if catch_all_seen_at is not None:
                errors.append(
                    f"Multiple catch-all routes found. "
                    f"First at route {catch_all_seen_at + 1}, again at route {i + 1}."
                )
            catch_all_seen_at = i

            if i != len(routes) - 1:
                warnings.append(
                    f"Catch-all route '{name}' is not last; later routes may be unreachable."
                )

        if catch_all_seen_at is not None and i > catch_all_seen_at:
            warnings.append(
                f"Route '{name}' appears after a catch-all route and may never match."
            )

        for ext in normalized_exts:
            if ext == "*":
                continue
            if ext in seen_extensions:
                warnings.append(
                    f"Extension '{ext}' in route '{name}' was already matched earlier by "
                    f"route '{seen_extensions[ext]}'. First-match routing means this later rule "
                    f"may be ineffective for that extension."
                )
            else:
                seen_extensions[ext] = name

    return errors, warnings


@router.get("/extractor-routes")
async def get_extractor_routes():
    return load_extractor_routes_file()


@router.put("/extractor-routes")
async def put_extractor_routes(payload: dict):
    errors, warnings = validate_routes(payload)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    path = extractor_routes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")

    return {
        "ok": True,
        "message": "extractor routes updated.",
        "path": str(path),
        "routes": payload.get("routes", []),
        "warnings": warnings,
    }