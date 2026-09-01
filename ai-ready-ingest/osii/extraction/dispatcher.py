from pathlib import Path

from osii.extraction.banyan_extractor import PdfDefaultExtractor
from osii.extraction.tika_extractor import TikaCatchallExtractor
from osii.extraction.native_text_extractor import NativeTextExtractor


def dispatch_extract(
    *,
    extractor_name: str,
    source_path: Path,
    data_volume_root: Path,
    osii_store: Path,
    expert_context: str | None = None,
    extractor_config: dict | None = None,
) -> dict:
    if extractor_name == "native_text":
        extractor = NativeTextExtractor()
    elif extractor_name in {"tika", "tika_catchall"}:
        extractor = TikaCatchallExtractor()
    elif extractor_name in {"banyan_ingest", "banyan-extract", "banyan", "pdf_default"}:
        extractor = PdfDefaultExtractor()
    else:
        from osii.processors.remote import RemoteExtractor, resolve_remote_processor

        descriptor = resolve_remote_processor(extractor_name, "extractor")
        extractor = RemoteExtractor(descriptor)

    return extractor.extract(
        source_path=source_path,
        data_volume_root=data_volume_root,
        osii_store=osii_store,
        expert_context=expert_context,
        extractor_config=extractor_config,
    )
