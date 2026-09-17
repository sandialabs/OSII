import json

import faiss
import numpy as np
import pytest

from osii.indexing.common import (
    _embed_batch,
    build_index_tmp_path,
    build_mapping_tmp_path,
    load_resumable_checkpoint,
)


def test_embedding_context_error_is_not_retried(monkeypatch):
    class ContextLimitedClient:
        calls = 0

        def embed(self, *, model, texts):
            self.calls += 1
            raise RuntimeError("the input length exceeds the context length")

    client = ContextLimitedClient()
    monkeypatch.setattr(
        "osii.indexing.common.time.sleep",
        lambda _: (_ for _ in ()).throw(AssertionError("context errors must not sleep")),
    )

    with pytest.raises(RuntimeError, match="exceeds the context length"):
        _embed_batch(client, "small-model", ["too long"], retries=3)
    assert client.calls == 1


def test_resume_truncates_mapping_rows_newer_than_faiss_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("OSII_DEFAULT_EMBEDDER", "test.embedder")
    monkeypatch.setenv("EMBEDDING_MODEL", "test-model")
    index = faiss.IndexFlatIP(2)
    index.add(np.asarray([[1.0, 0.0]], dtype="float32"))
    faiss.write_index(index, str(build_index_tmp_path(tmp_path)))
    rows = [{"faiss_id": 0}, {"faiss_id": 1}]
    build_mapping_tmp_path(tmp_path).write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    restored_index, restored_rows = load_resumable_checkpoint(tmp_path)

    assert restored_index.ntotal == 1
    assert restored_rows == [{"faiss_id": 0}]
    assert build_mapping_tmp_path(tmp_path).read_text(encoding="utf-8").count("\n") == 1
