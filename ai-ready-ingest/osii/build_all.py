import argparse
import subprocess
import sys
from pathlib import Path


def run_step(cmd: list[str], *, cwd: Path, label: str) -> None:
    print("")
    print(f"=== {label} ===")
    print("Command:")
    print(" ".join(f'"{part}"' if " " in str(part) else str(part) for part in cmd))

    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"Step failed: {label}")


def main():
    parser = argparse.ArgumentParser(
        description="Run the full OSII backend build pipeline."
    )
    parser.add_argument("--data-root", required=True, help="Path to source data root")
    parser.add_argument("--osii-root", required=True, help="Path to .osii root")

    parser.add_argument("--include-pattern", action="append", default=[], help="Include glob pattern (repeatable)")
    parser.add_argument("--exclude-pattern", action="append", default=[], help="Exclude glob pattern (repeatable)")
    parser.add_argument("--max-files", type=int, default=None, help="Optional max files limit")

    parser.add_argument("--extractor", default="textract", help="Extractor override for all files")
    parser.add_argument("--synthesizer", default="describe", help="File/object synthesizer")
    parser.add_argument("--folder-synthesizer", default="describe_folder", help="Folder synthesizer")
    parser.add_argument("--context", default="", help="Optional expert context")

    parser.add_argument(
        "--collection-file",
        action="append",
        default=[],
        help="Optional collection definition TOML file to import after build (repeatable)",
    )
    parser.add_argument(
        "--collection-synthesizer",
        default=None,
        help="Optional collection synthesizer name to run for imported collections",
    )
    parser.add_argument(
        "--collection-synth-max-chars",
        type=int,
        default=4000,
        help="Max chars for collection_firstn or similar simple collection synthesis",
    )

    parser.add_argument(
        "--enricher",
        action="append",
        default=[],
        help="Optional enricher name to run after synthesis (repeatable)",
    )
    parser.add_argument(
        "--enricher-scope-type",
        default="root",
        choices=["root", "object", "folder", "collection"],
        help="Scope type for enrichment if not collection-driven",
    )
    parser.add_argument("--enricher-file-id", default=None, help="Object scope file_id for enrichment")
    parser.add_argument("--enricher-folder-id", default=None, help="Folder scope folder_id for enrichment")
    parser.add_argument("--enricher-collection-id", default=None, help="Collection scope collection_id for enrichment")

    parser.add_argument("--build-embeddings", action="store_true", help="Build embeddings and lexical index")
    parser.add_argument("--embedding-model", default=None, help="Optional embedding model override")
    parser.add_argument("--batch-size", type=int, default=1, help="Embedding batch size")
    parser.add_argument("--checkpoint-every", type=int, default=100, help="Checkpoint frequency")
    parser.add_argument(
        "--chunking-method",
        default="paragraph",
        choices=["paragraph", "window"],
        help="Chunking strategy for search index build",
    )
    parser.add_argument("--chunk-size", type=int, default=1200, help="Chunk size for window chunking")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap for window chunking")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    python_exe = sys.executable

    data_root = Path(args.data_root).resolve()
    osii_root = Path(args.osii_root).resolve()

    # Step 1: extraction + optional file/folder synthesis through build_collection
    build_cmd = [
        python_exe,
        "-m",
        "osii.build_collection",
        "--data-root",
        str(data_root),
        "--osii-root",
        str(osii_root),
    ]

    for pattern in args.include_pattern:
        build_cmd.extend(["--include-pattern", pattern])

    for pattern in args.exclude_pattern:
        build_cmd.extend(["--exclude-pattern", pattern])

    if args.max_files is not None:
        build_cmd.extend(["--max-files", str(args.max_files)])

    if args.extractor:
        build_cmd.extend(["--extractor", args.extractor])

    if args.synthesizer:
        build_cmd.extend(["--synthesizer", args.synthesizer])

    if args.folder_synthesizer:
        build_cmd.extend(["--folder-synthesizer", args.folder_synthesizer])

    if args.context:
        build_cmd.extend(["--context", args.context])

    run_step(build_cmd, cwd=repo_root, label="Build collection")

    # Step 2: optional collection imports
    imported_collection_names = []

    for collection_file in args.collection_file:
        collection_cmd = [
            python_exe,
            "-m",
            "osii.create_collection",
            "--osii-root",
            str(osii_root),
            "--file",
            str(Path(collection_file).resolve()),
            "--update-if-exists",
        ]
        run_step(collection_cmd, cwd=repo_root, label=f"Import collection: {collection_file}")

        imported_collection_names.append(str(Path(collection_file).resolve()))

    # Step 3: optional collection synthesis
    if args.collection_synthesizer:
        if args.collection_synthesizer != "collection_firstn":
            raise RuntimeError(
                f"Unsupported collection synthesizer in build_all: {args.collection_synthesizer}"
            )

        if not args.collection_file and not args.enricher_collection_id:
            print("")
            print("No collection files were imported and no explicit collection id was provided for collection synthesis.")
            print("Skipping collection synthesis.")
        else:
            from osii.domain.scopes.collections import list_collections

            collections = list_collections(osii_root)

            for collection in collections:
                collection_id = collection["id"]

                synth_cmd = [
                    python_exe,
                    "-c",
                    (
                        "from osii.synthesis.collection.firstn import CollectionFirstNSynthesizer; "
                        f"CollectionFirstNSynthesizer().synthesize_collection("
                        f"osii_store=r'{osii_root}', "
                        f"collection_id=r'{collection_id}', "
                        f"expert_context={repr(args.context or None)}, "
                        f"synthesizer_config={{'max_chars': {args.collection_synth_max_chars}}}"
                        ")"
                    ),
                ]
                run_step(
                    synth_cmd,
                    cwd=repo_root,
                    label=f"Collection synthesis: {collection['name']}",
                )

    # Step 4: optional enrichments
    for enricher_name in args.enricher:
        if args.enricher_scope_type == "root":
            enrich_cmd = [
                python_exe,
                "-m",
                "osii.enrich_scope",
                "--osii-root",
                str(osii_root),
                "--enricher",
                enricher_name,
                "--scope-type",
                "root",
            ]
        elif args.enricher_scope_type == "object":
            if not args.enricher_file_id:
                raise RuntimeError("--enricher-file-id is required for object enrichment scope")
            enrich_cmd = [
                python_exe,
                "-m",
                "osii.enrich_scope",
                "--osii-root",
                str(osii_root),
                "--enricher",
                enricher_name,
                "--scope-type",
                "object",
                "--file-id",
                args.enricher_file_id,
            ]
        elif args.enricher_scope_type == "folder":
            if not args.enricher_folder_id:
                raise RuntimeError("--enricher-folder-id is required for folder enrichment scope")
            enrich_cmd = [
                python_exe,
                "-m",
                "osii.enrich_scope",
                "--osii-root",
                str(osii_root),
                "--enricher",
                enricher_name,
                "--scope-type",
                "folder",
                "--folder-id",
                args.enricher_folder_id,
            ]
        elif args.enricher_scope_type == "collection":
            if not args.enricher_collection_id:
                raise RuntimeError("--enricher-collection-id is required for collection enrichment scope")
            enrich_cmd = [
                python_exe,
                "-m",
                "osii.enrich_scope",
                "--osii-root",
                str(osii_root),
                "--enricher",
                enricher_name,
                "--scope-type",
                "collection",
                "--collection-id",
                args.enricher_collection_id,
            ]
        else:
            raise RuntimeError(f"Unsupported enricher scope type: {args.enricher_scope_type}")

        run_step(enrich_cmd, cwd=repo_root, label=f"Enrichment: {enricher_name}")

    # Step 5: optional embeddings + lexical index
    if args.build_embeddings:
        embed_cmd = [
            python_exe,
            "-m",
            "osii.build_vector_index",
            "--osii-root",
            str(osii_root),
            "--batch-size",
            str(args.batch_size),
            "--checkpoint-every",
            str(args.checkpoint_every),
            "--chunking-method",
            args.chunking_method,
            "--chunk-size",
            str(args.chunk_size),
            "--chunk-overlap",
            str(args.chunk_overlap),
        ]

        if args.embedding_model:
            embed_cmd.extend(["--embedding-model", args.embedding_model])

        run_step(embed_cmd, cwd=repo_root, label="Build embeddings and lexical index")

    print("")
    print("All requested pipeline steps completed successfully.")


if __name__ == "__main__":
    main()