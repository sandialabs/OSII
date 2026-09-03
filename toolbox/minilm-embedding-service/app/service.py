"""Embedding model service implementation."""

from typing import List

from sentence_transformers import SentenceTransformer

from app.config import Settings


class EmbeddingService:
    """Service wrapper for model loading and embedding generation.

    Parameters
    ----------
    settings : Settings
        Application settings.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = SentenceTransformer(
            self.settings.model_name,
            device="cpu",
            local_files_only=True,
            tokenizer_kwargs={"clean_up_tokenization_spaces": True},
        )

    def embed(
        self,
        texts: List[str],
        batch_size: int,
        normalize: bool,
    ) -> List[List[float]]:
        """Generate embeddings for input texts.

        Parameters
        ----------
        texts : list[str]
            Input texts to embed.
        batch_size : int
            Batch size for model inference.
        normalize : bool
            Whether to L2-normalize embeddings.

        Returns
        -------
        list[list[float]]
            Embedding vectors as nested Python lists.
        """
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()
