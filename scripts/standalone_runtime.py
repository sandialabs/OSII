"""PyInstaller entry script; the installed executable never invokes a shell."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from osii.desktop.runtime import main
    raise SystemExit(main())
