"""Shared topic projection. No storage, network, or application mode dependencies."""
import numpy as np

# Bound dense document vectors, not the number of catalog entries. Chunk vectors
# are streamed by the adapters; projection workspace is linear in this matrix.
MAX_DOCUMENT_VECTOR_BYTES = 64 * 1024 * 1024


class TopicIndexUnavailable(ValueError):
    """The selected index needs to be built, rebuilt, or narrowed."""


def project_documents(vectors: np.ndarray) -> tuple[np.ndarray, float]:
    """Deterministic approximate PCA for large spaces, exact for small spaces.

    A fixed-seed, oversampled subspace with four power iterations avoids the
    full corpus SVD. Only the small subspace is decomposed; every document
    contributes to centering, fitting, coordinates and explained variance.
    """
    coordinates = np.zeros((len(vectors), 2))
    if len(vectors) < 2:
        return coordinates, 0.0
    centered = np.array(vectors, dtype=np.float32, copy=True)
    centered -= centered.mean(axis=0, dtype=np.float64).astype(np.float32)
    energy = float(np.einsum("ij,ij->", centered, centered, dtype=np.float64))
    if energy <= 1e-20:
        return coordinates, 0.0
    try:
        if min(centered.shape) <= 32:
            _, _, axes = np.linalg.svd(centered, full_matrices=False)
        else:
            width = min(12, *centered.shape)
            probe = np.random.default_rng(0).standard_normal((centered.shape[1], width)).astype(np.float32)
            basis, _ = np.linalg.qr(centered @ probe, mode="reduced")
            for _ in range(4):
                feature_basis, _ = np.linalg.qr(centered.T @ basis, mode="reduced")
                basis, _ = np.linalg.qr(centered @ feature_basis, mode="reduced")
            _, _, axes = np.linalg.svd(basis.T @ centered, full_matrices=False)
        rank = min(2, len(axes))
        coordinates[:, :rank] = centered @ axes[:rank].T
    except np.linalg.LinAlgError as exc:
        raise TopicIndexUnavailable("The projection could not be calculated. Choose a smaller scope or rebuild embeddings.") from exc
    for axis in range(rank):
        if axes[axis, np.abs(axes[axis]).argmax()] < 0:
            coordinates[:, axis] *= -1
    variance = float(np.einsum("ij,ij->", coordinates, coordinates) / energy)
    return coordinates, min(1.0, max(0.0, variance))
