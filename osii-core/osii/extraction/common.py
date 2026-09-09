import mimetypes
from pathlib import Path

from osii.domain.storage.ids import compute_file_id, sha256_hex
from osii.domain.storage.objects import (
    append_manifest_record,
    append_text_file,
    iso_mtime_utc,
    write_artifact_bytes,
    write_meta_toml,
    write_provenance_toml,
)


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def init_doc_context(source_path: Path, data_volume_root: Path) -> dict:
    src = source_path.resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Source file not found: {src}")

    try:
        source_relpath = src.relative_to(data_volume_root.resolve()).as_posix()
    except ValueError:
        source_relpath = src.name

    try:
        size_bytes = src.stat().st_size
    except Exception:
        size_bytes = None

    return {
        "src": src,
        "source_relpath": source_relpath,
        "file_id": compute_file_id(src),
        "sha256_hex": sha256_hex(src),
        "size_bytes": size_bytes,
        "mtime_utc": iso_mtime_utc(src),
        "mime": guess_mime(src),
    }


def initialize_bundle(
    *,
    osii_store: Path,
    doc_ctx: dict,
) -> None:
    write_meta_toml(
        osii_store=osii_store,
        file_id=doc_ctx["file_id"],
        source_relpath=doc_ctx["source_relpath"],
        filename=doc_ctx["src"].name,
        mime=doc_ctx["mime"],
        size_bytes=doc_ctx["size_bytes"],
        mtime_utc=doc_ctx["mtime_utc"],
        sha256_hex=doc_ctx["sha256_hex"],
    )


def update_provenance(
    *,
    osii_store: Path,
    doc_ctx: dict,
    extractor_name: str,
    extractor_version: str,
    status: str,
    tools: dict | None,
    config: dict | None,
    state,
) -> None:
    write_provenance_toml(
        osii_store=osii_store,
        file_id=doc_ctx["file_id"],
        pipeline_version="osii-v1-draft",
        status=status,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        tools=tools,
        config=config,
        counts={
            # remove segments_written
            "segments_written": state.segments_written,
            "artifacts_written": state.artifacts_written,
            "units_attempted": state.units_attempted,
            "units_completed": state.units_completed,
        },
        errors=(
            {
                "message": state.error,
                "warnings": state.warnings,
            }
            if state.error or state.warnings
            else None
        ),
    )


def persist_segment(
    *,
    osii_store: Path,
    doc_ctx: dict,
    segment,
    shared_text_file: bool = True,
) -> str:
    seg_id = f"seg-{segment.seg:06d}"

    if shared_text_file:
        char_start, char_end = append_text_file(
            osii_store=osii_store,
            file_id=doc_ctx["file_id"],
            text=segment.text or "",
        )

        record = {
            "kind": "text",
            "id": seg_id,
            "path": "text.txt",
            "type": segment.type,
            "span": {
                "char_start": char_start,
                "char_end": char_end,
            },
            "source_origin": segment.source_origin,
        }
        if segment.related_ids:
            record["related_ids"] = segment.related_ids

        append_manifest_record(
            osii_store=osii_store,
            file_id=doc_ctx["file_id"],
            record=record,
        )
        return seg_id

    raise RuntimeError("Only shared_text_file=True is supported in the current architecture.")


def persist_artifact(
    *,
    osii_store: Path,
    doc_ctx: dict,
    artifact,
    artifact_num: int,
) -> str:
    artifact_path = write_artifact_bytes(
        osii_store=osii_store,
        file_id=doc_ctx["file_id"],
        artifact_num=artifact_num,
        extension=artifact.extension,
        data=artifact.data,
    )
    rel_path = f"artifacts/{artifact_path.name}"

    record = {
        "kind": artifact.kind,
        "id": artifact.artifact_id,
        "path": rel_path,
        "type": artifact.type,
        "source_origin": artifact.source_origin,
    }
    if artifact.related_ids:
        record["related_ids"] = artifact.related_ids

    append_manifest_record(
        osii_store=osii_store,
        file_id=doc_ctx["file_id"],
        record=record,
    )
    return artifact.artifact_id


def build_result_dict(doc_ctx: dict, error: str | None = None) -> dict:
    return {
        "src": str(doc_ctx["src"]),
        "file_id": doc_ctx["file_id"],
        "source_relpath": doc_ctx["source_relpath"],
        "osii_rel": str((Path("objects") / doc_ctx["file_id"]).as_posix()),
        "error": error,
    }