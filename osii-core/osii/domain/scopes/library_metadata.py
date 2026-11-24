"""Summarize recorded locations and document fields without reading the source drive."""

from collections import Counter
from pathlib import PurePosixPath, PureWindowsPath


_FIELDS = ("author", "agency", "document_type", "date", "title")
_MAX_GROUPS = 250


class LibraryMetadata:
    def __init__(self, source_root):
        self.source_root = str(source_root)
        self.locations = Counter()
        self.fields = {field: Counter() for field in _FIELDS}

    def add(self, source_relpath, absolute_path, metadata):
        recorded = str(source_relpath or "").replace("\\", "/").strip("/")
        browse_path = recorded.rpartition("/")[0]
        if isinstance(absolute_path, str) and absolute_path:
            location = PureWindowsPath(absolute_path) if PureWindowsPath(absolute_path).drive else PurePosixPath(absolute_path)
            label = str(location.parent) if location.is_absolute() else browse_path
        else:
            label = browse_path
        self.locations[(label or "Location not recorded", browse_path)] += 1

        for field, counts in self.fields.items():
            value = (metadata.get(field) or {}).get("value")
            if isinstance(value, str) and value.strip():
                counts[" ".join(value.split())] += 1

    def summary(self):
        return {
            "source_root": self.source_root,
            "locations": [{"label": label, "browse_path": path, "count": count}
                          for (label, path), count in self.locations.most_common(_MAX_GROUPS)],
            "location_count": len(self.locations),
            "document_fields": {
                field: {
                    "recorded_count": sum(counts.values()),
                    "distinct_count": len(counts),
                    "rows": [{"label": value, "count": count} for value, count in counts.most_common(_MAX_GROUPS)],
                }
                for field, counts in self.fields.items()
            },
        }
