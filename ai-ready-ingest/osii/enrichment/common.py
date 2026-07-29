from __future__ import annotations

from pathlib import Path

from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.artifacts.text_representations import get_preferred_text_representation


def collect_scope_texts(osii_root: Path, scope: dict) -> tuple[list[dict], int]:
    file_ids = list_scope_file_ids(osii_root, scope)
    items = []
    total_chars = 0

    for file_id in file_ids:
        preferred = get_preferred_text_representation(osii_root, file_id)
        if preferred is None:
            continue

        text = preferred.get("text") or ""
        total_chars += len(text)

        items.append(
            {
                "file_id": file_id,
                "representation": preferred.get("name"),
                "kind": preferred.get("kind"),
                "path": preferred.get("path"),
                "text": text,
            }
        )

    return items, total_chars