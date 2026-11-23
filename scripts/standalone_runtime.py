"""PyInstaller entry script; the installed executable never invokes a shell."""
import multiprocessing
from pathlib import Path
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if not getattr(sys, "frozen", False):
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "osii-processor-modules" / "embeddinggemma"))
    from osii.desktop.runtime import main
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
