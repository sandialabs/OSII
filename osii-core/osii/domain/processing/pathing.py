from pathlib import Path


def path_within(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except Exception:
        return False


def display_rel(path: Path, shared_root: Path, upload_root: Path) -> str:
    p = path.resolve()
    if path_within(shared_root, p):
        return f"my_data/{p.relative_to(shared_root).as_posix()}" if p != shared_root else "my_data"
    if path_within(upload_root, p):
        return f"uploaded_data/{p.relative_to(upload_root).as_posix()}" if p != upload_root else "uploaded_data"
    return p.name


def derive_osii_base(source_path: Path, data_volume_root: Path, osii_root: Path) -> Path:
    src = source_path.resolve()
    rel = src.relative_to(data_volume_root.resolve())
    return osii_root.resolve() / rel.parent / src.stem


def derive_text_artifact_path(source_path: Path, data_volume_root: Path, osii_root: Path) -> Path:
    return derive_osii_base(source_path, data_volume_root, osii_root).with_suffix(".txt")


def derive_datacard_path(source_path: Path, data_volume_root: Path, osii_root: Path) -> Path:
    return derive_osii_base(source_path, data_volume_root, osii_root).with_suffix(".osii")