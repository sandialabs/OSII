"""Keep generation instructions and temporary source addresses out of wiki prose."""

import re


_DERIVED_SOURCE_LINE = re.compile(
    r"(?mi)^[ \t]*[-*+] [`]?\[derived-batch-[^\]\n]+\][`]?[ \t]+[—–-][ \t]+Derived batch [^\n]+\n?"
)
_DERIVED_REFERENCE = re.compile(r"[`]?(?:\[derived-batch-[^\]\n]+\])[`]?", re.IGNORECASE)
_CONTEXT_MARKER = re.compile(
    r"(?im)^[ \t>*#_`-]*Human-provided expert context\s*:[*_ `]*"
)
_HEADING = re.compile(r"(?m)^#{1,6} .+")
_SOURCES_HEADING = re.compile(r"(?i)^#{2,6}\s+(?:Sources|Source documents)\s*$")
_MARKDOWN_FENCE = re.compile(r"\A```(?:markdown|md)?\s*\n(.*)\n```\Z", re.I | re.S)


def clean_wiki_markdown(markdown: str, *, guidance: tuple[str, ...] = ()) -> str:
    """Remove known generation scaffolding while leaving the article intact."""
    text = markdown.strip()
    if fenced := _MARKDOWN_FENCE.fullmatch(text):
        text = fenced[1].strip()
    # The API sends guidance in distinct messages. Remove verbatim echoes from
    # the opening; the original settings remain part of run provenance.
    opening_heading = _HEADING.search(text, pos=1)
    opening_end = opening_heading.start() if opening_heading else len(text)
    opening, article = text[:opening_end], text[opening_end:]
    for block in guidance:
        block = block.strip()
        if block:
            opening = opening.replace(block, "")
    # Older wikis echoed this exact role label and everything up to the first
    # article heading. The saved revision is still available for editing.
    if marker := _CONTEXT_MARKER.search(opening):
        opening = opening[:marker.start()]
    if opening.strip() and article:
        text = f"{opening.rstrip()}\n\n{article}"
    else:
        text = opening.strip() or article
    text = _DERIVED_SOURCE_LINE.sub("", text)
    text = _DERIVED_REFERENCE.sub("", text)
    lines = text.rstrip().splitlines()
    if lines and _SOURCES_HEADING.fullmatch(lines[-1].strip()):
        lines.pop()
    return "\n".join(lines).strip()


def has_wiki_body(markdown: str) -> bool:
    for line in markdown.splitlines():
        value = line.strip()
        if _SOURCES_HEADING.fullmatch(value):
            break
        if value and not value.startswith(("#", "```", "---")):
            return True
    return False
