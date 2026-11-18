"""Compatibility shim; Apache Tika HTTP implementation lives in its processor module."""
from osii.extraction.base import BaseExtractor


class TikaCatchallExtractor(BaseExtractor):
    name = "tika_catchall"
    display_name = "Apache Tika"
    description = "Uses the independently deployed OSII Tika adapter. Configure its Apache Tika endpoint in Setup."
    version = "2.0"

    def extract(self, **kwargs):
        from osii.processors.remote import RemoteExtractor, resolve_remote_processor
        return RemoteExtractor(resolve_remote_processor("tika", "extractor")).extract(**kwargs)


def extract(**kwargs):
    return TikaCatchallExtractor().extract(**kwargs)
