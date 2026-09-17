def build_system_prompt() -> str:
    return (
        "You are a careful assistant answering questions over a grounded OSII corpus. "
        "Use the provided retrieval evidence and do not invent facts. "
        "If the evidence is weak or incomplete, say so clearly."
    )


def build_user_prompt(*, query: str, scope: dict, history: list[dict], evidence: list[dict]) -> str:
    history_text = "\n".join(
        f"{turn.get('role', 'user').upper()}: {turn.get('content', '')}"
        for turn in history
    ) or "(no prior history)"
    evidence_text = "\n\n".join(
        f"[{index}] file_id={item.get('file_id')} source_relpath={item.get('source_relpath')} "
        f"chunk_id={item.get('chunk_id')} char_start={item.get('char_start')} char_end={item.get('char_end')}\n"
        f"snippet: {item.get('snippet')}"
        for index, item in enumerate(evidence, start=1)
    ) or "(no evidence)"
    return f"""Query:
{query}

Scope:
{scope}

Conversation history:
{history_text}

Evidence:
{evidence_text}

Instructions:
- Answer the query using the evidence above.
- Prefer precise, grounded statements.
- If evidence is insufficient, say so.
- Return only the answer text.
"""
