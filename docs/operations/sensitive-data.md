# Sensitive data, transfer, and deletion

OSII keeps sensitivity awareness beside each document without pretending that
metadata is an access-control system. Open a document, choose **Labels & Tags**,
and record:

- one or more sensitivity labels, such as a locally approved marking;
- plain-text tags for topics or local handling categories;
- optional handling notes for the next human who receives the sidecar.

These values are written to
`.osii/objects/<file-id>/governance.toml`. The file is canonical, inspectable,
and included when the object travels in an OSII package. Labels do not encrypt
files, authenticate users, prevent export, or enforce corporate policy. Apply
the receiving environment's normal controls to both the originals and `.osii`.

## Share or merge a collection

Open a collection and choose **Export OSII Package**. The ZIP contains the
collection descriptor, member object sidecars, and `osii-package.json`. It does
not contain original source files. The manifest records every included path,
size, and SHA-256 checksum.

On the receiving OSII, open **Collections** and choose **Import OSII package**.
Before writing anything, OSII rejects unsafe paths, missing files, extra files,
unsupported versions, oversize archives, and checksum mismatches. Merge rules
are intentionally conservative:

- a new file ID adds the object sidecar;
- an existing file ID keeps the local extracted content and derived products;
- sensitivity labels and tags are unioned case-insensitively so importing
  cannot silently weaken local awareness;
- distinct collection-name or ID conflicts create an `imported` collection;
- source files are never created or overwritten;
- corpus-wide search and embedding indexes are removed and must be rebuilt,
  preventing mixed or stale vector spaces.

Imported documents are immediately browsable from their sidecars. Run the
normal Intake **Process library** workflow when you want to rebuild embeddings;
BM25 rebuilds from the remaining canonical text when lexical search next needs
it.

## Delete one document safely

Open the document and choose **Delete File Data**. Select one explicit mode:

1. **Remove OSII data only** deletes extracted text, provenance, enrichments,
   collection/folder membership, affected aggregate products, matching Activity
   run records, and corpus-wide indexes. The original remains and can be taken
   in again.
2. **Remove the original file and all OSII data** performs the same purge and
   also deletes the resolved source file. This option requires write access to
   the source folder; read-only deployments should use the first mode and have
   the source owner remove the original separately.

OSII first returns an impact preview. Deletion requires the full file ID and a
token tied to that exact preview. If the source, memberships, active jobs, or
derived state changes, the token becomes stale and the user must review again.
Queued or running Intake work blocks deletion.

Aggregate folder, collection, and root products may contain excerpts from the
deleted file, so they are removed rather than guessed at surgically. All BM25,
hashing, and semantic indexes are derived and are also removed. Rebuild the
products you still need from the remaining canonical sidecars.

## API endpoints

- `GET|PUT /api/objects/{file_id}/governance`
- `GET /api/collections/{collection_id}/export`
- `POST /api/packages/import` with multipart field `package`
- `POST /api/objects/{file_id}/deletion-preview`
- `DELETE /api/objects/{file_id}` with `mode`, `preview_token`, and
  `confirmation`

The backend publishes live schemas and try-it forms at
<http://127.0.0.1:8511/docs>.
