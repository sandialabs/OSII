"""Shared topic projection. No storage, network, or application mode dependencies."""
import numpy as np


class TopicIndexUnavailable(ValueError):
    """The selected index needs to be built, rebuilt, or narrowed."""


def project_documents(vectors: np.ndarray) -> tuple[np.ndarray, float]:
    """Deterministic PCA, with stable axis signs and defined degenerate output."""
    coordinates = np.zeros((len(vectors), 2))
    if len(vectors) < 2:
        return coordinates, 0.0
    centered = vectors - vectors.mean(axis=0)
    try:
        u, singular, axes = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError as exc:
        raise TopicIndexUnavailable("The projection could not be calculated. Choose a smaller scope or rebuild embeddings.") from exc
    rank = min(2, len(singular))
    coordinates[:, :rank] = u[:, :rank] * singular[:rank]
    for axis in range(rank):
        if axes[axis, np.abs(axes[axis]).argmax()] < 0:
            coordinates[:, axis] *= -1
    energy = float(np.sum(singular ** 2))
    return coordinates, float(np.sum(singular[:rank] ** 2) / energy) if energy > 1e-20 else 0.0

