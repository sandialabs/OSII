import argparse
from pathlib import Path

from osii.domain.scopes.collection_files import (
    load_collection_definition,
    parse_collection_metadata,
    resolve_collection_members,
)
from osii.domain.scopes.collections import (
    add_documents_to_collection,
    create_collection,
    get_collection,
    list_collections,
    update_collection,
)


def find_collection_by_name(osii_root: Path, name: str) -> dict | None:
    for item in list_collections(osii_root):
        if item.get("name") == name:
            return item
    return None


def main():
    parser = argparse.ArgumentParser(description="Create or update a collection from a TOML definition file.")
    parser.add_argument("--osii-root", required=True, help="Path to the .osii root")
    parser.add_argument("--file", required=True, help="Path to collection TOML file")
    parser.add_argument(
        "--update-if-exists",
        action="store_true",
        help="Update an existing collection with the same name instead of failing",
    )

    args = parser.parse_args()

    osii_root = Path(args.osii_root).resolve()
    collection_file = Path(args.file).resolve()

    payload = load_collection_definition(collection_file)
    metadata = parse_collection_metadata(payload)
    file_ids = resolve_collection_members(osii_root, payload)

    existing = find_collection_by_name(osii_root, metadata["name"])

    if existing and not args.update_if_exists:
        raise RuntimeError(
            f"Collection already exists with name '{metadata['name']}'. "
            f"Use --update-if-exists to update it."
        )

    if existing:
        collection = update_collection(
            osii_root,
            existing["id"],
            name=metadata["name"],
            description=metadata["description"],
            kind=metadata["kind"],
            color=metadata["color"],
        )
        collection_id = existing["id"]
        action = "updated"
    else:
        collection = create_collection(
            osii_root,
            name=metadata["name"],
            description=metadata["description"],
            kind=metadata["kind"],
            color=metadata["color"],
        )
        collection_id = collection["id"]
        action = "created"

    membership_result = add_documents_to_collection(osii_root, collection_id, file_ids)

    print(f"Collection {action}: {metadata['name']}")
    print(f"Collection ID: {collection_id}")
    print(f"Members added: {len(membership_result['added'])}")
    print(f"Already present: {len(membership_result['already_present'])}")


if __name__ == "__main__":
    main()