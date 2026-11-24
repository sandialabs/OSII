"""Prepare a reading view without changing saved wiki revisions."""

from osii.processor_sdk.wiki import clean_wiki_markdown, has_wiki_body


def wiki_reading_fields(history: dict) -> dict:
    data = history.get("data") or {}
    if data.get("artifact_type") != "wiki_markdown":
        return {}
    current = history.get("current")
    if any(
        revision["id"] == current and revision.get("origin") == "human"
        for revision in history["revisions"]
    ):
        return {}
    markdown = data.get("markdown") or ""
    cleaned = clean_wiki_markdown(markdown)
    if cleaned != markdown.strip():
        return {"reading_markdown": cleaned if has_wiki_body(cleaned) else ""}
    return {}
