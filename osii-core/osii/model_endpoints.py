"""Deployment-owned model endpoints; no store, framework, or processor dependency."""
from dataclasses import dataclass, field
import os
from pathlib import Path
from collections.abc import Mapping
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ModelEndpoint:
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    model: str = ""
    credential_env: str = ""

    def public(self) -> dict:
        return {"base_url": self.base_url, "model": self.model,
                "configured": bool(self.base_url), "credential_present": bool(self.api_key)}


def _url(value: str, capability: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    try:
        url = urlsplit(value)
        valid = (url.scheme in {"http", "https"} and url.hostname and not url.username
                 and not url.password and not url.query and not url.fragment)
        _ = url.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"Invalid {capability} API base URL; use HTTP(S) without credentials, query, or fragment")
    return value


def endpoint_from_environment(capability: str, *, default_url: str = "",
                              environment: Mapping[str, str] | None = None) -> ModelEndpoint:
    """Explicit capability URLs never inherit another endpoint's credentials.

    A capability key/file can also override a legacy shared endpoint's key.
    Files take precedence over inline keys; an unreadable configured file fails
    closed. Reranking never inherits the chat/embedding endpoint or key.
    """
    if capability not in {"chat", "embedding", "rerank"}:
        raise ValueError("Unsupported model endpoint capability")
    env = os.environ if environment is None else environment
    prefix = f"OSII_{capability.upper()}"
    specific_url = env.get(prefix + "_BASE_URL", "").strip()
    shared_url = "" if capability == "rerank" else (
        env.get("OSII_MODEL_BASE_URL", "").strip() or env.get("OPENAI_BASE_URL", "").strip() or default_url)
    url = _url(specific_url or shared_url, capability)
    names = [prefix + "_API_KEY"]
    if capability != "rerank" and not specific_url:
        names.extend(["OSII_MODEL_API_KEY", "OPENAI_API_KEY"])
    selected = names[0]
    if capability != "rerank" and not specific_url:
        selected = "OSII_MODEL_API_KEY" if env.get("OSII_MODEL_BASE_URL", "").strip() else "OPENAI_API_KEY"
    key = ""
    for name in names:
        path = env.get(name + "_FILE", "").strip()
        if path:
            try:
                file = Path(path).expanduser()
                if file.stat().st_size > 65536:
                    raise ValueError()
                key = file.read_text(encoding="utf-8").strip()
            except (OSError, ValueError):
                raise ValueError(f"Cannot read configured {capability} API key file") from None
            selected = name
            break
        if env.get(name, ""):
            key, selected = env[name], name
            break
    if "\n" in key or "\r" in key:
        raise ValueError(f"Invalid {capability} API key: line breaks are not allowed")
    model = env.get(prefix + "_MODEL", "").strip()
    if not model and capability != "rerank":
        model = env.get(f"OPENAI_{capability.upper()}_MODEL", "").strip()
    return ModelEndpoint(url, key, model, selected)
