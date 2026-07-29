from app.prompts import build_system_prompt, build_user_prompt
import requests


def _message_content(msg) -> str:
    if msg is None:
        return ""
    if isinstance(msg, dict):
        return msg.get("content") or ""
    return getattr(msg, "content", None) or ""


def run_chat_completion(
    *,
    provider: str,
    ollama_base_url: str | None = None,
    openai_compatible_base_url: str | None = None,
    openai_compatible_api_key: str | None = None,
    model: str,
    max_tokens: int,
    query: str,
    scope: dict,
    history: list[dict],
    evidence: list[dict],
) -> str:
    if provider == "extractive":
        useful = [
            item for item in evidence
            if (item.get("snippet") or "").strip()
        ]
        if not useful:
            return "I could not find grounded text in this scope to answer the question."
        lines = [
            f"- {(item.get('snippet') or '').strip()} "
            f"[{item.get('filename') or item.get('file_id') or 'source'}]"
            for item in useful[:5]
        ]
        return (
            "The locally available evidence most relevant to your question is:\n\n"
            + "\n".join(lines)
            + "\n\nThis answer uses the offline extractive fallback; verify the cited passages for interpretation."
        )

    if provider == "ollama":
        response = requests.post(
            f"{(ollama_base_url or 'http://localhost:11434').rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": build_user_prompt(query=query, scope=scope, history=history, evidence=evidence)},
                ],
                "options": {"num_predict": max_tokens},
            },
            timeout=120,
        )
        response.raise_for_status()
        return (response.json().get("message", {}).get("content") or "").strip() or "[EMPTY_MODEL_OUTPUT]"

    if provider not in {"openai", "openai_compatible"}:
        raise ValueError(f"Unsupported CHAT_PROVIDER: {provider}")
    if not openai_compatible_base_url:
        raise ValueError("CHAT_PROVIDER=openai requires OSII_CHAT_BASE_URL or OSII_MODEL_BASE_URL.")

    headers = {"Content-Type": "application/json"}
    if openai_compatible_api_key:
        headers["Authorization"] = f"Bearer {openai_compatible_api_key}"
    response = requests.post(
        f"{openai_compatible_base_url.rstrip('/')}/chat/completions",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": build_user_prompt(query=query, scope=scope, history=history, evidence=evidence)},
            ],
            "max_tokens": max_tokens,
        },
        headers=headers,
        timeout=120,
    )
    response.raise_for_status()
    choices = response.json().get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
    return (_message_content(message) or "").strip() or "[EMPTY_MODEL_OUTPUT]"
