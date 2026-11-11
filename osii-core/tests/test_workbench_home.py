import json
from types import SimpleNamespace
import faiss
import numpy as np
from osii.domain import workbench_local as home
from osii.indexing.common import embedding_namespace


def test_home_dismissal_is_persisted_and_no_text_or_vectors_are_loaded(
    client, temp_osii_root, sample_osii_object, monkeypatch
):
    (
        temp_osii_root / "objects" / sample_osii_object["file_id"] / "provenance.toml"
    ).write_text('[provenance]\nstatus="done"\n')
    from osii.domain.read.sidecar import SidecarLibraryReader

    monkeypatch.setattr(
        SidecarLibraryReader,
        "get_representation",
        lambda *args: (_ for _ in ()).throw(AssertionError("Home read document text")),
    )
    monkeypatch.setattr(
        faiss,
        "read_index",
        lambda *args: (_ for _ in ()).throw(AssertionError("Home loaded vectors")),
    )
    monkeypatch.setattr(
        home,
        "get_chat_settings",
        lambda root: SimpleNamespace(chat_provider_chain=("extractive",)),
    )
    result = client.get("/api/workbench/home")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["documents"] == 1 and data["tools"]["search"]["enabled"]
    assert (
        not data["tools"]["chat"]["enabled"] and not data["tools"]["topics"]["enabled"]
    )
    assert data["setup"]["visible"]
    assert client.post("/api/admin/setup/dismiss", json={}).status_code == 200
    assert not home.local_home(temp_osii_root)["setup"]["visible"]
    assert json.loads((temp_osii_root / "state/home.json").read_text())[
        "setup_dismissed"
    ]
    assert "text" not in data and "api_key" not in result.text


def test_metadata_readiness_rejects_stale_mismatched_and_broken_indexes(
    temp_osii_root, sample_osii_object, monkeypatch
):
    root = temp_osii_root
    fid = sample_osii_object["file_id"]
    (root / "objects" / fid / "provenance.toml").write_text(
        '[provenance]\nstatus="done"\n'
    )
    monkeypatch.setattr(
        home, "selected_processor", lambda *args, **kw: "openai.embedder"
    )
    monkeypatch.setattr(home, "selected_model", lambda *args, **kw: "test-model")
    monkeypatch.setattr(
        home,
        "get_chat_settings",
        lambda root: SimpleNamespace(
            chat_provider_chain=("openai",), openai_chat_model="chat"
        ),
    )
    provider, model = embedding_namespace(
        provider="openai.embedder", model="test-model"
    )
    directory = root / "embeddings/providers" / provider / model
    directory.mkdir(parents=True)
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1.0, 0.0]], dtype="float32"))
    faiss.write_index(index, str(directory / "segments.faiss"))
    (directory / "segments.mapping.jsonl").write_text(
        json.dumps({"faiss_id": 0, "file_id": fid}) + "\n"
    )
    meta = directory / "segments.meta.toml"
    meta.write_text(
        '[embeddings]\nsemantic=true\nprovider="openai.embedder"\nmodel="test-model"\ncount=1\ndimension=2\n'
    )
    monkeypatch.setattr(
        faiss,
        "read_index",
        lambda *args: (_ for _ in ()).throw(AssertionError("Home loaded vectors")),
    )
    assert home.local_home(root)["tools"]["topics"]["enabled"]
    monkeypatch.setattr(
        home, "get_artifact_staleness", lambda *args: {"stale": {"embeddings": True}}
    )
    assert not home.local_home(root)["tools"]["topics"]["enabled"]
    monkeypatch.setattr(home, "get_artifact_staleness", lambda *args: {})
    meta.write_text(meta.read_text().replace("dimension=2", "dimension=3"))
    assert not home.local_home(root)["tools"]["topics"]["enabled"]
    meta.write_text(meta.read_text().replace("dimension=3", "dimension=2"))
    (directory / "segments.faiss").write_bytes(b"corrupt")
    assert not home.local_home(root)["tools"]["topics"]["enabled"]
