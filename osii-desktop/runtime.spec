"""One-folder runtime. Build from the monorepo root on the target OS."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
payload = root / "osii-desktop" / "resources"
services = ["osii_local_extractor", "osii_local_tesseract", "osii_local_synthesizer",
            "osii_local_embedder", "osii_local_enricher", "osii_model_provider_bridge"]
hidden = collect_submodules("osii") + collect_submodules("uvicorn")
for service in services:
    hidden += collect_submodules(service)
data = collect_data_files("osii") + collect_data_files("bm25s")
for file in ("nist-cloud-computing.pdf", "README.md"):
    data.append((str(root / "scripts" / "demo-data" / file), "scripts/demo-data"))
for package in ("osii", "jsonschema", "jsonschema_specifications", "referencing", "tqdm"):
    data += copy_metadata(package)
data.append((str(payload / "ocr"), "ocr"))
if (root / "osii-core" / "config").is_dir():
    data.append((str(root / "osii-core" / "config"), "config"))
if (payload / "dashboard").is_dir():
    data.append((str(payload / "dashboard"), "dashboard"))
data.append((str(payload / "release.json"), "."))
data.append((str(payload / "THIRD_PARTY_NOTICES.txt"), "."))

a = Analysis([str(root / "scripts" / "standalone_runtime.py")],
    pathex=[str(root / "osii-core")], binaries=[], datas=data, hiddenimports=hidden,
    excludes=["pytest", "IPython", "tkinter", "haystack", "torch", "cv2", "sqlalchemy", "psycopg"],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="osii-runtime",
          # Keep pipe stdio available while hiding consoles owned by spawned helpers.
          debug=False, strip=False, upx=False, console=True, hide_console="hide-early")
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="osii-runtime")
