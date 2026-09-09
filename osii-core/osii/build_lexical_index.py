import argparse
from pathlib import Path

from osii.domain.storage.store import (
    embeddings_chunks_manifest_path,
    embeddings_lexical_index_path,
    embeddings_lexical_meta_path,
)
from osii.indexing.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNKING_METHOD,
    SUPPORTED_CHUNKING_METHODS,
    write_chunk_manifest,
)
from osii.search.lexical import build_bm25_index


def main():
    parser = argparse.ArgumentParser(
        description="Build a BM25 lexical index over derived text chunks without calling the embedding model."
    )
    parser.add_argument(
        "--osii-root",
        required=True,
        help="Path to the .osii root",
    )
    parser.add_argument(
        "--chunking-method",
        default=DEFAULT_CHUNKING_METHOD,
        choices=SUPPORTED_CHUNKING_METHODS,
        help="Chunking strategy used before lexical indexing.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Maximum characters per overlapping chunk.",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help="Target character overlap between adjacent chunks.",
    )

    args = parser.parse_args()

    osii_root = Path(args.osii_root).resolve()
    if not osii_root.exists():
        raise RuntimeError(f"OSII root does not exist: {osii_root}")

    print(f"Building lexical index under {osii_root}")
    print(f"Chunking method: {args.chunking_method}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Chunk overlap: {args.chunk_overlap}")

    chunk_manifest_path, rows = write_chunk_manifest(
        osii_root,
        method=args.chunking_method,
        chunk_size=args.chunk_size,
        overlap=args.chunk_overlap,
    )

    index_path, meta_path = build_bm25_index(osii_root)

    print("")
    print("Lexical index build complete.")
    print(f"  chunks manifest : {chunk_manifest_path}")
    print(f"  chunk count     : {len(rows)}")
    print(f"  lexical index   : {index_path}")
    print(f"  lexical meta    : {meta_path}")
    print(f"  expected index path : {embeddings_lexical_index_path(osii_root)}")
    print(f"  expected meta path  : {embeddings_lexical_meta_path(osii_root)}")
    print(f"  expected chunk path : {embeddings_chunks_manifest_path(osii_root)}")


if __name__ == "__main__":
    main()
