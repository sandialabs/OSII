import argparse
from pathlib import Path

from osii.domain.read.catalog import load_files_catalog, load_folders_catalog
from osii.domain.read.folder_synthesis import get_folder_synthesis_text
from osii.domain.storage.store import ensure_osii_store_layout, root_synth_path, object_dir
from osii.domain.processing.synth_routing import load_object_synth_routes, load_folder_synth_routes, choose_object_synthesizer, choose_folder_synthesizer, get_extensions_for_synthesizer
from osii.domain.artifacts.folder_overview import build_folder_overview
from osii.domain.artifacts.root_overview import build_root_overview
from osii.synthesis.folder_registry import resolve_folder_synthesizer
from osii.synthesis.registry import resolve_synthesizer

def main():
    parser = argparse.ArgumentParser(description="Run hierarchy synthesis over an existing OSII store.")
    parser.add_argument("--osii-root", required=True, help="Path to the .osii root")
    parser.add_argument("--synthesizer", default=None, help="Object-level synthesizer override")
    parser.add_argument("--folder-synthesizer", default=None, help="Folder-level synthesizer override")
    parser.add_argument("--objects-only", action="store_true", help="Only synthesize objects")
    parser.add_argument("--folders-only", action="store_true", help="Only synthesize folders")
    parser.add_argument("--root-only", action="store_true", help="Only regenerate root overview and root synth")
    parser.add_argument("--context", default="", help="Optional expert context")

    args = parser.parse_args()

    osii_root = Path(args.osii_root).resolve()
    ensure_osii_store_layout(osii_root)

    object_count = 0
    folder_count = 0
    root_count = 0

    object_synth_routes = load_object_synth_routes()
    folder_synth_routes = load_folder_synth_routes()

    if not args.folders_only and not args.root_only:
        files = load_files_catalog(osii_root)

        for entry in files:
            file_id = entry.get("file_id")
            source_relpath = entry.get("source_relpath", "")
            if not file_id:
                continue

            synth_name = args.synthesizer or choose_object_synthesizer(Path(source_relpath), object_synth_routes)
            if not synth_name:
                continue

            print(f"Synthesizing object {file_id} with {synth_name}")
            synthesizer = resolve_synthesizer(synth_name)
            
            if "image" in synth_name:
                extensions = get_extensions_for_synthesizer(object_synth_routes, synth_name)
                artifact_path = object_dir(osii_root, file_id) / "artifacts" 

                for artifact in artifact_path.iterdir():
                    if artifact.suffix.lower() in extensions:
                        synthesizer.synthesize(
                            osii_store=osii_root,
                            file_id=file_id,
                            image=artifact.name,
                            expert_context=args.context or None,
                            synthesizer_config={},
                        )
                        object_count += 1
            else:
                synthesizer.synthesize(
                    osii_store=osii_root,
                    file_id=file_id,
                    expert_context=args.context or None,
                    synthesizer_config={},
                )
                object_count += 1

    folders = load_folders_catalog(osii_root)
    folders_sorted = sorted(
        folders,
        key=lambda f: len(((f.get("path") or "").strip("/")).split("/")) if (f.get("path") or "").strip("/") else 0,
        reverse=True,
    )

    if not args.objects_only:
        for entry in folders_sorted:
            folder_id = entry.get("folder_id")
            folder_relpath = (entry.get("path") or "").strip("/")
            if not folder_id:
                continue

            build_folder_overview(osii_root, folder_id)

            if args.root_only and folder_relpath != "":
                continue

            synth_name = args.folder_synthesizer or choose_folder_synthesizer(folder_relpath, folder_synth_routes)
            if not synth_name:
                continue

            print(f"Synthesizing folder {folder_relpath or '[root]'} with {synth_name}")
            synthesizer = resolve_folder_synthesizer(synth_name)
            synthesizer.synthesize_folder(
                osii_store=osii_root,
                folder_id=folder_id,
                expert_context=args.context or None,
                synthesizer_config={},
            )
            folder_count += 1

    # root overview and root synth
    build_root_overview(osii_root)

    root_folder = None
    for entry in folders:
        relpath = (entry.get("path") or "").strip("/")
        if relpath == "":
            root_folder = entry
            break

    if root_folder:
        root_folder_id = root_folder.get("folder_id")
        if root_folder_id:
            root_text = get_folder_synthesis_text(osii_root, root_folder_id)
            if root_text:
                root_synth_path(osii_root).write_text(root_text, encoding="utf-8")
                root_count = 1

    print("")
    print("Synthesis complete.")
    print(f"  objects synthesized : {object_count}")
    print(f"  folders synthesized : {folder_count}")
    print(f"  root synthesized    : {root_count}")


if __name__ == "__main__":
    main()