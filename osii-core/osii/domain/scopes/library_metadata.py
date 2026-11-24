"""Summarize recorded locations and document fields without reading the source drive."""

import tomllib
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath

from osii.domain.document_metadata import metadata_source
from osii.domain.storage.store import provenance_path


_FIELDS = ("author", "agency", "document_type", "date", "title")
_MAX_GROUPS = 250


def sidecar_file_properties(root: Path, file_id: str) -> dict:
    try:
        provenance = tomllib.loads(provenance_path(root, file_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    metadata = provenance.get("response_metadata")
    properties = metadata.get("file_properties") if isinstance(metadata, dict) else None
    return properties if isinstance(properties, dict) else {}


def _saved_field(field, labels, file_properties):
    metadata = labels.get("document_metadata") or {}
    suggestion = (metadata.get(field) or {}).get("value")
    recorded = file_properties.get(field)
    source = metadata_source(labels, field)
    if source[0] == "edited" and suggestion:
        return suggestion, source
    if isinstance(recorded, str) and recorded.strip():
        return recorded, ("file", None)
    return suggestion, source


class LibraryMetadata:
    def __init__(self, source_root):
        self.source_root = str(source_root)
        self.locations = Counter()
        self.fields = {field: defaultdict(Counter) for field in _FIELDS}

    def add(self, source_relpath, absolute_path, labels, file_properties=None):
        recorded = str(source_relpath or "").replace("\\", "/").strip("/")
        browse_path = recorded.rpartition("/")[0]
        if isinstance(absolute_path, str) and absolute_path:
            location = PureWindowsPath(absolute_path) if PureWindowsPath(absolute_path).drive else PurePosixPath(absolute_path)
            label = str(location.parent) if location.is_absolute() else browse_path
        else:
            label = browse_path
        self.locations[(label or "Location not recorded", browse_path)] += 1

        file_properties = file_properties if isinstance(file_properties, dict) else {}
        for field, groups in self.fields.items():
            value, source = _saved_field(field, labels, file_properties)
            if isinstance(value, str) and value.strip():
                label = " ".join(value.split())
                if field == "document_type":
                    label = label.casefold().capitalize()
                groups[label][source] += 1

    def _field_summary(self, groups):
        counts = Counter({label: sources.total() for label, sources in groups.items()})
        return {
            "recorded_count": counts.total(),
            "distinct_count": len(counts),
            "rows": [
                {
                    "label": label,
                    "count": count,
                    "sources": [
                        {"kind": kind, "processor": processor, "count": source_count}
                        for (kind, processor), source_count in groups[label].most_common()
                    ],
                }
                for label, count in counts.most_common(_MAX_GROUPS)
            ],
        }

    def summary(self):
        return {
            "source_root": self.source_root,
            "locations": [{"label": label, "browse_path": path, "count": count}
                          for (label, path), count in self.locations.most_common(_MAX_GROUPS)],
            "location_count": len(self.locations),
            "document_fields": {field: self._field_summary(groups) for field, groups in self.fields.items()},
        }
