# Collection file format

## Purpose

Collections are first-class backend scopes. A collection definition file provides a portable way to create or update a logical collection of objects independently of the source folder hierarchy.

## Format

The current collection definition format is TOML.

## Example

```toml
[collection]
name = "thermal-set"
description = "Collection for thermal documents"
kind = "file-list"
color = "#3366ff"

[[members]]
source_relpath = "purcell.pdf"

[[members]]
file_id = "sha256-test123"
```

## Collection metadata

The `[collection]` table may include:

- `name`
- `description`
- `kind`
- `color`

`name` is required.

## Member entries

Each `[[members]]` entry must include one of:

- `file_id`
- `source_relpath`

When `source_relpath` is provided, the backend resolves it to the corresponding object identifier using the current OSII catalog.

## Semantics

Collections are logical scopes. They are independent of folder hierarchy and may be used for:

- search
- chat
- synthesis
- future enrichments
- future wiki generation

## CLI usage

```powershell
python -m osii.create_collection `
  --osii-root ".\osii-data\.osii" `
  --file ".\config\my_collection.toml"
```

To update an existing collection with the same name:

```powershell
python -m osii.create_collection `
  --osii-root ".\osii-data\.osii" `
  --file ".\config\my_collection.toml" `
  --update-if-exists
```
