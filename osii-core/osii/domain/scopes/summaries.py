from __future__ import annotations

from pathlib import Path

from osii.domain.artifacts.object_summaries import get_object_summaries
from osii.domain.scopes.membership import list_scope_file_ids


def get_scope_object_summaries(osii_root: Path, scope: dict) -> dict:
    file_ids = list_scope_file_ids(osii_root, scope)
    summaries = get_object_summaries(osii_root, file_ids)

    return {
        "scope": scope,
        "summaries": summaries,
    }