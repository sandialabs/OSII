import re
from pathlib import Path

from osii.domain.read.manifest import list_text_records
from osii.domain.read.segments import get_segment_text
from osii.domain.storage.store import object_dir, object_synth_text_path
from osii.domain.storage.objects import update_synthesis_provenance


def ensure_object_synth_dir(osii_store: Path, file_id: str) -> Path:
    obj_dir = object_dir(osii_store, file_id).resolve()
    obj_dir.mkdir(parents=True, exist_ok=True)
    return obj_dir


def read_concatenated_text(osii_store: Path, file_id: str) -> tuple[str, int]:
    records = list_text_records(osii_store, file_id)
    texts = []

    for record in records:
        seg_id = record.get("id", "")
        if not seg_id.startswith("seg-"):
            continue
        try:
            seg_num = int(seg_id.removeprefix("seg-"))
        except Exception:
            continue

        text = get_segment_text(osii_store, file_id, seg_num)
        if text:
            texts.append(text)

    return "\n\n".join(texts), len(records)


def light_clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def write_synth_text(
    *,
    osii_store: Path,
    file_id: str,
    text: str,
    synthesizer_name: str | None = None,
    synthesizer_version: str | None = None,
    config: dict | None = None,
    expert_context_used: bool = False,
) -> Path:
    ensure_object_synth_dir(osii_store, file_id)
    path = object_synth_text_path(osii_store, file_id)
    path.write_text(text, encoding="utf-8")

    if synthesizer_name and synthesizer_version:
        update_synthesis_provenance(
            osii_store=osii_store,
            file_id=file_id,
            synthesizer_name=synthesizer_name,
            synthesizer_version=synthesizer_version,
            config=config,
            expert_context_used=bool(expert_context_used),
        )

    return path