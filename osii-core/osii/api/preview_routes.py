from pathlib import Path
import tomllib

from fastapi import APIRouter, Request

from osii.domain.processing.intake import expand_queue_to_files, parse_patterns
from osii.domain.processing.pathing import display_rel, path_within

router = APIRouter(prefix="/api", tags=["preview"])


def normalize_user_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    cleaned = str(raw).strip().strip('"').strip("'")
    if not cleaned:
        return None
    return Path(cleaned).expanduser()


def safe_resolve_user_path(raw: str | None, fallback: Path) -> Path:
    p = normalize_user_path(raw)
    if p is None:
        return fallback.resolve()
    try:
        return p.resolve()
    except Exception:
        return fallback.resolve()


def load_parser_routes(config_path: Path) -> list[dict]:
    if not config_path.exists():
        return [{"name": "default-tika", "extractor": "tika", "extensions": ["*"]}]
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return data.get("routes", [])


def load_parsers(config_path: Path) -> list[dict]:
    if not config_path.exists():
        return []
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return data.get("extractors", [])


def choose_parser(path: Path, routes: list[dict]) -> str:
    suffix = path.suffix.lower()
    for route in routes:
        exts = route.get("extensions", [])
        if "*" in exts or suffix in [e.lower() for e in exts]:
            return route["extractor"]
    return "tika"


@router.post("/preview/extractors")
async def preview_parsers(request: Request, payload: dict):
    shared_root = request.app.state.shared_volume_root.resolve()
    upload_root = request.app.state.upload_originals_root.resolve()

    queue_paths = payload.get("queue_paths", [])
    include_subfolders = bool(payload.get("include_subfolders", True))
    show_hidden = bool(payload.get("show_hidden", False))

    raw_include = payload.get("include_patterns", "")
    raw_exclude = payload.get("exclude_patterns", "")

    include_patterns = parse_patterns("\n".join(raw_include) if isinstance(raw_include, list) else raw_include)
    exclude_patterns = parse_patterns("\n".join(raw_exclude) if isinstance(raw_exclude, list) else raw_exclude)

    max_files = payload.get("max_files")
    max_total_size_mb = payload.get("max_total_size_mb")

    max_files_int = int(max_files) if max_files not in (None, "") else None
    max_total_size = int(float(max_total_size_mb) * 1024 * 1024) if max_total_size_mb not in (None, "") else None

    queue_items = []
    for raw in queue_paths:
        p = safe_resolve_user_path(raw, shared_root)
        if p.exists():
            queue_items.append(
                {
                    "path": str(p),
                    "display": display_rel(p, shared_root, upload_root),
                    "kind": "folder" if p.is_dir() else "file",
                    "source": "shared" if path_within(shared_root, p) else "upload",
                }
            )

    resolved_files, preview = expand_queue_to_files(
        queue_items=queue_items,
        include_subfolders=include_subfolders,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        show_hidden=show_hidden,
        max_files=max_files_int,
        max_total_size=max_total_size,
        shared_root=shared_root,
        upload_root=upload_root,
    )

    parser_routes = load_parser_routes(Path("config/parser_routes.toml").resolve())
    parser_registry = load_parsers(Path("config/extractors.toml").resolve())
    parser_map = {p["id"]: p for p in parser_registry if p.get("id")}

    items = []
    for p in resolved_files:
        parser_id = choose_parser(p, parser_routes)
        parser_info = parser_map.get(parser_id)
        items.append(
            {
                "path": str(p),
                "display": display_rel(p, shared_root, upload_root),
                "extractor": parser_id,
                "parser_exists": parser_info is not None,
                "parser_enabled": parser_info.get("enabled", False) if parser_info else False,
                "parser_display_name": parser_info.get("display_name", "") if parser_info else "",
            }
        )

    return {
        "preview": preview,
        "items": items,
    }
