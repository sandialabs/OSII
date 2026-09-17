from pathlib import Path


def ensure_osii_store_layout(osii_store: Path) -> dict[str, Path]:
    root = osii_store.resolve()

    paths = {
        "root": root,
        "folders": root / "folders",
        "objects": root / "objects",
        "runs": root / "runs",
        "embeddings": root / "embeddings",
        "collections": root / "collections",
    }

    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    return paths


def root_toml_path(osii_store: Path) -> Path:
    return ensure_osii_store_layout(osii_store)["root"] / "root.toml"


def root_synth_path(osii_store: Path) -> Path:
    return ensure_osii_store_layout(osii_store)["root"] / "root.synth.txt"


def collection_toml_path(osii_store: Path) -> Path:
    return root_toml_path(osii_store)


def object_dir(osii_store: Path, file_id: str) -> Path:
    return ensure_osii_store_layout(osii_store)["objects"] / file_id


def object_synth_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "synth.txt"


def artifacts_dir(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "artifacts"


def meta_toml_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "meta.toml"


def provenance_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "provenance.toml"


def manifest_jsonl_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "manifest.jsonl"


def folder_manifest_path(osii_store: Path, folder_id: str) -> Path:
    return ensure_osii_store_layout(osii_store)["folders"] / f"folder-{folder_id}.toml"


def folder_synth_path(osii_store: Path, folder_id: str) -> Path:
    return ensure_osii_store_layout(osii_store)["folders"] / f"folder-{folder_id}.synth.txt"


def run_metadata_path(osii_store: Path, run_name: str) -> Path:
    return ensure_osii_store_layout(osii_store)["runs"] / f"{run_name}.toml"


def embeddings_dir(osii_store: Path) -> Path:
    return ensure_osii_store_layout(osii_store)["embeddings"]


def embeddings_index_path(osii_store: Path) -> Path:
    return embeddings_dir(osii_store) / "segments.faiss"


def embeddings_mapping_path(osii_store: Path) -> Path:
    return embeddings_dir(osii_store) / "segments.mapping.jsonl"


def embeddings_meta_path(osii_store: Path) -> Path:
    return embeddings_dir(osii_store) / "segments.meta.toml"


def embeddings_chunks_dir(osii_store: Path) -> Path:
    path = embeddings_dir(osii_store) / "chunks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def embeddings_chunks_manifest_path(osii_store: Path) -> Path:
    return embeddings_chunks_dir(osii_store) / "chunks.jsonl"


def object_synth_toml_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "synth.toml"


def object_synth_text_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "synth.txt"


def image_synth_toml_path(osii_store: Path, file_id: str, image: str) -> Path:
    return object_dir(osii_store, file_id) / f"synth_{image.split('.')[0]}.toml"


def image_synth_text_path(osii_store: Path, file_id: str, image: str) -> Path:
    return object_dir(osii_store, file_id) / f"synth_{image.split('.')[0]}.txt"


def folder_overview_path(osii_store: Path, folder_id: str) -> Path:
    return ensure_osii_store_layout(osii_store)["folders"] / f"folder-{folder_id}.overview.toml"


def folder_synth_toml_path(osii_store: Path, folder_id: str) -> Path:
    return ensure_osii_store_layout(osii_store)["folders"] / f"folder-{folder_id}.synth.toml"


def folder_synth_text_path(osii_store: Path, folder_id: str) -> Path:
    return ensure_osii_store_layout(osii_store)["folders"] / f"folder-{folder_id}.synth.txt"


def root_overview_path(osii_store: Path) -> Path:
    return ensure_osii_store_layout(osii_store)["root"] / "root.overview.toml"


def root_synth_toml_path(osii_store: Path) -> Path:
    return ensure_osii_store_layout(osii_store)["root"] / "root.synth.toml"


def root_synth_text_path(osii_store: Path) -> Path:
    return ensure_osii_store_layout(osii_store)["root"] / "root.synth.txt"


def object_text_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "text.txt"


def object_syntheses_dir(osii_store: Path, file_id: str) -> Path:
    path = object_dir(osii_store, file_id) / "syntheses"
    path.mkdir(parents=True, exist_ok=True)
    return path


def object_enrichments_dir(osii_store: Path, file_id: str) -> Path:
    path = object_dir(osii_store, file_id) / "enrichments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def folder_syntheses_dir(osii_store: Path, folder_id: str) -> Path:
    path = ensure_osii_store_layout(osii_store)["folders"] / f"folder-{folder_id}.syntheses"
    path.mkdir(parents=True, exist_ok=True)
    return path


def folder_enrichments_dir(osii_store: Path, folder_id: str) -> Path:
    path = ensure_osii_store_layout(osii_store)["folders"] / f"folder-{folder_id}.enrichments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def collections_dir(osii_store: Path) -> Path:
    return ensure_osii_store_layout(osii_store)["collections"]


def collection_dir(osii_store: Path, collection_id: str) -> Path:
    path = collections_dir(osii_store) / collection_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def collection_syntheses_dir(osii_store: Path, collection_id: str) -> Path:
    path = collection_dir(osii_store, collection_id) / "syntheses"
    path.mkdir(parents=True, exist_ok=True)
    return path


def collection_enrichments_dir(osii_store: Path, collection_id: str) -> Path:
    path = collection_dir(osii_store, collection_id) / "enrichments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def root_syntheses_dir(osii_store: Path) -> Path:
    path = ensure_osii_store_layout(osii_store)["root"] / "syntheses"
    path.mkdir(parents=True, exist_ok=True)
    return path


def root_enrichments_dir(osii_store: Path) -> Path:
    path = ensure_osii_store_layout(osii_store)["root"] / "enrichments"
    path.mkdir(parents=True, exist_ok=True)
    return path

def embeddings_lexical_dir(osii_store: Path) -> Path:
    path = embeddings_dir(osii_store) / "lexical"
    path.mkdir(parents=True, exist_ok=True)
    return path


def embeddings_lexical_index_path(osii_store: Path) -> Path:
    return embeddings_lexical_dir(osii_store) / "bm25_index.pkl"


def embeddings_lexical_meta_path(osii_store: Path) -> Path:
    return embeddings_lexical_dir(osii_store) / "bm25_meta.json"