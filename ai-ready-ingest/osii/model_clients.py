from __future__ import annotations

from typing import Any


def create_shirty_client() -> Any:
    """Load the optional corporate model client only when a connected feature runs."""
    try:
        from shirty.client import ShirtyClient
    except ImportError as exc:
        raise RuntimeError(
            "This processor requires the optional Shirty model client. "
            "Install OSII with the 'connected' extra in an environment where "
            "the corporate package is available, or select a local processor."
        ) from exc
    return ShirtyClient()

