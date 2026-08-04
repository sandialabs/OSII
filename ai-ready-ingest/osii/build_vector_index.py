import argparse
import os
from pathlib import Path

from osii.indexing.common import (
    embed_collection_resumable,
    get_embedding_model,
)


def main():
    parser = argparse.ArgumentParser(description="Build a FAISS vector database over derived text chunks.")
    parser.add_argument(
        "--osii-root",
        required=True,
        help="Path to the .osii root",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Embedding batch size (default is conservative for robustness).",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Embedding model override (default uses EMBEDDING_MODEL env var or built-in default).",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Checkpoint FAISS index every N successful embeddings.",
    )
    parser.add_argument(
        "--chunking-method",
        default="paragraph",
        choices=["paragraph", "window"],
        help="Chunking strategy used before embedding.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
        help="Chunk size for window chunking.",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Chunk overlap for window chunking.",
    )

    args = parser.parse_args()

    osii_root = Path(args.osii_root).resolve()
    if not osii_root.exists():
        raise RuntimeError(f"OSII root does not exist: {osii_root}")

    model_name = get_embedding_model(args.embedding_model)
    # All path helpers use this explicit identity so checkpoints and reads stay
    # inside one provider/model vector space.
    os.environ["EMBEDDING_MODEL"] = model_name

    print(f"Building embeddings under {osii_root}")
    print(f"Model: {model_name}")
    print(f"Batch size: {args.batch_size}")
    print(f"Checkpoint every: {args.checkpoint_every} successful embeddings")
    print(f"Chunking method: {args.chunking_method}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Chunk overlap: {args.chunk_overlap}")

    index_path, mapping_path, meta_path = embed_collection_resumable(
        osii_root,
        model=model_name,
        batch_size=args.batch_size,
        checkpoint_every=args.checkpoint_every,
        chunking_method=args.chunking_method,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    print("")
    print("Vector build complete.")
    print(f"  model   : {model_name}")
    print(f"  index   : {index_path}")
    print(f"  mapping : {mapping_path}")
    print(f"  meta    : {meta_path}")


if __name__ == "__main__":
    main()
