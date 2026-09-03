"""Application configuration for the embedding service."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the service.

    Attributes
    ----------
    model_name : str
        Hugging Face model identifier.
    host : str
        Host address for the HTTP server.
    port : int
        Port for the HTTP server.
    default_batch_size : int
        Default batch size used during embedding requests.
    max_batch_size : int
        Maximum allowed batch size.
    max_texts : int
        Maximum number of texts allowed per request.
    max_chars_per_text : int
        Maximum number of characters allowed per text.
    normalize_embeddings : bool
        Whether embeddings should be normalized by default.
    """

    model_name: str
    host: str
    port: int
    default_batch_size: int
    max_batch_size: int
    max_texts: int
    max_chars_per_text: int
    normalize_embeddings: bool


def _get_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable.

    Parameters
    ----------
    name : str
        Environment variable name.
    default : bool
        Default value if the variable is missing.

    Returns
    -------
    bool
        Parsed boolean value.
    """
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    """Load application settings from environment variables.

    Returns
    -------
    Settings
        Parsed application settings.
    """
    return Settings(
        model_name=os.getenv(
            "MODEL_NAME",
            "sentence-transformers/all-MiniLM-L6-v2",
        ),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8085")),
        default_batch_size=int(os.getenv("DEFAULT_BATCH_SIZE", "16")),
        max_batch_size=int(os.getenv("MAX_BATCH_SIZE", "128")),
        max_texts=int(os.getenv("MAX_TEXTS", "128")),
        max_chars_per_text=int(os.getenv("MAX_CHARS_PER_TEXT", "50000")),
        normalize_embeddings=_get_bool("NORMALIZE_EMBEDDINGS", True),
    )
