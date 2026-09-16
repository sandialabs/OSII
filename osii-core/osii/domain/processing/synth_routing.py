import tomllib
from osii.configuration import load_tools_config
from pathlib import Path


def object_synth_routes_path() -> Path:
    return Path("config/object_synth_routes.toml").resolve()


def folder_synth_routes_path() -> Path:
    return Path("config/folder_synth_routes.toml").resolve()


def load_object_synth_routes(config_path: Path | None = None) -> list[dict]:
    if config_path is None:
        routes = load_tools_config().get("routes", {}).get("object_synthesis")
        if isinstance(routes, list):
            return routes
        return [
            {"name": "reports-describe", "synthesizer": "describe", "extensions": [".pdf", ".docx"]},
            {"name": "generic-describe", "synthesizer": "describe", "extensions": ["*"]},
        ]

    if not config_path.exists():
        return load_object_synth_routes()
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return data.get("routes", [])


def load_folder_synth_routes(config_path: Path | None = None) -> list[dict]:
    if config_path is None:
        routes = load_tools_config().get("routes", {}).get("folder_synthesis")
        if isinstance(routes, list):
            return routes
        return [
            {"name": "experiments-recursive", "synthesizer": "recursive_folder", "path_patterns": ["experiments/**", "runs/**", "reports/**", "analysis/**"]},
            {"name": "simulation-folders-recursive", "synthesizer": "recursive_folder", "path_patterns": ["simulation/**", "simulations/**", "thermal/**"]},
            {"name": "catchall-describe", "synthesizer": "describe_folder", "path_patterns": ["*"]},
        ]

    if not config_path.exists():
        return load_folder_synth_routes()
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return data.get("routes", [])


def choose_object_synthesizer(path: Path, routes: list[dict]) -> str | None:
    suffix = path.suffix.lower()
    for route in routes:
        exts = [e.lower() for e in route.get("extensions", [])]
        if "*" in exts or suffix in exts:
            return route.get("synthesizer")
    return None


def get_extensions_for_synthesizer(
    object_synth_routes: list[dict], synthesizer_name: str
) -> list[str] | None:
    for route in object_synth_routes:
        if route.get("synthesizer") == synthesizer_name:
            return route.get("extensions", [])
    return None


def choose_folder_synthesizer(folder_relpath: str, routes: list[dict]) -> str | None:
    import fnmatch

    rel = folder_relpath.replace("\\", "/").strip("/")
    for route in routes:
        patterns = route.get("path_patterns", [])
        if any(
            fnmatch.fnmatch(rel, pattern.strip("/")) or pattern == "*"
            for pattern in patterns
        ):
            return route.get("synthesizer")
    return None
