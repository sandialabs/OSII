from pathlib import Path


SYNTHESIS_DIR = Path(__file__).resolve().parent


def load_prompt(scope_family: str, name: str | None = None) -> str:
    if name is None:
        # Backward-compatible mode:
        # load_prompt("filename.txt") -> look in legacy shared prompts dir
        path = SYNTHESIS_DIR / "prompts" / scope_family
    else:
        path = SYNTHESIS_DIR / scope_family / "prompts" / name

    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    return path.read_text(encoding="utf-8")