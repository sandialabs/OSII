import hashlib
import uuid
from pathlib import Path


def sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_file_id(path: Path) -> str:
    return f"sha256-{sha256_hex(path)}"


def new_folder_id() -> str:
    return str(uuid.uuid4())


def new_intake_id() -> str:
    return str(uuid.uuid4())