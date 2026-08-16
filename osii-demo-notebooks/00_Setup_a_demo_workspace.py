# %%
from pathlib import Path

# Put your documents in this folder beside the notebooks.
DOCUMENTS_DIR = Path("documents")

documents = sorted(path for path in DOCUMENTS_DIR.rglob("*") if path.is_file())
if not documents:
    raise RuntimeError(f"No documents found in {DOCUMENTS_DIR.resolve()}")

print(f"Found {len(documents)} document(s) in {DOCUMENTS_DIR.resolve()}:")
for document in documents:
    print("-", document.relative_to(DOCUMENTS_DIR))
