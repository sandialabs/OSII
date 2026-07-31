"""Fail when a local Markdown link in README.md or docs/ is broken."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s", "-", text)


def anchors(path: Path) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        base = slug(match.group(1))
        count = counts.get(base, 0)
        counts[base] = count + 1
        found.add(base if count == 0 else f"{base}-{count}")
    return found


def markdown_files() -> list[Path]:
    files = {ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))}
    for path in ROOT.rglob("README.md"):
        relative = path.relative_to(ROOT)
        if any(
            part in {
                ".git",
                ".pytest_cache",
                ".venv",
                "node_modules",
                "site",
                "venv",
            }
            or part == "__pycache__"
            for part in relative.parts
        ):
            continue
        files.add(path)
    return sorted(files)


def main() -> int:
    errors: list[str] = []
    for source in markdown_files():
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            for raw in LINK.findall(line):
                destination = raw.strip().strip("<>")
                if destination.startswith(("http://", "https://", "mailto:")):
                    continue
                destination = destination.split(maxsplit=1)[0]
                path_text, _, fragment = destination.partition("#")
                target = source if not path_text else (source.parent / unquote(path_text)).resolve()
                if target.is_dir():
                    target = target / "index.md"
                if not target.is_file():
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing {destination}"
                    )
                    continue
                if fragment and target.suffix.lower() == ".md" and unquote(fragment) not in anchors(target):
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing anchor #{fragment} in "
                        f"{target.relative_to(ROOT)}"
                    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Checked local links in {len(markdown_files())} Markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
