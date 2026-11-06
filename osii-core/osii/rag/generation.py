import requests

from osii.rag.config import ChatSettings
from osii.rag.prompts import build_system_prompt, build_user_prompt


def run_chat_completion(
    *,
    provider: str,
    settings: ChatSettings,
    model: str,
    query: str,
    scope: dict,
    history: list[dict],
    evidence: list[dict],
) -> str:
    if provider == "extractive":
        useful = [item for item in evidence if (item.get("snippet") or "").strip()]
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

    messages = [
        {"role": "system", "content": build_system_prompt()},
        {
            "role": "user",
            "content": build_user_prompt(
                query=query,
                scope=scope,
                history=history,
                evidence=evidence,
            ),
        },
    ]
    if provider == "ollama":
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": messages,
                "options": {"num_predict": settings.chat_max_tokens},
            },
            timeout=120,
        )
        response.raise_for_status()
        return (response.json().get("message", {}).get("content") or "").strip() or "[EMPTY_MODEL_OUTPUT]"

    if provider != "openai":
        raise ValueError(f"Unsupported CHAT_PROVIDER: {provider}")
    if not settings.openai_compatible_base_url:
        raise ValueError(f"CHAT_PROVIDER={provider} requires an OpenAI-compatible endpoint.")
    headers = {"Content-Type": "application/json"}
    if settings.openai_compatible_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_compatible_api_key}"
    response = requests.post(
        f"{settings.openai_compatible_base_url}/chat/completions",
        json={"model": model, "messages": messages, "max_tokens": settings.chat_max_tokens},
        headers=headers,
        timeout=120,
    )
    response.raise_for_status()
    choices = response.json().get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else ""
    return str(content or "").strip() or "[EMPTY_MODEL_OUTPUT]"


def complete_experiment_messages(*, provider: str, settings: ChatSettings, model: str,
                                 messages: list[dict], max_tokens: int) -> tuple[str, dict, str]:
    """One explicit experiment call. No retries or alternate-provider fallback."""
    if provider == "ollama":
        try:
            response = requests.post(f"{settings.ollama_base_url}/api/chat",
                json={"model": model, "stream": False, "format": "json", "messages": messages,
                      "options": {"num_predict": max_tokens}}, timeout=(5, 30))
            response.raise_for_status()
            data = response.json()
            return str(data.get("message", {}).get("content") or ""), {
                "prompt_tokens": data.get("prompt_eval_count"), "completion_tokens": data.get("eval_count")}, str(data.get("model") or model)
        except (requests.RequestException, ValueError):
            raise RuntimeError("The configured chat endpoint failed; no fallback was attempted") from None
    if provider != "openai":
        raise ValueError("No experiment chat model is configured")
    headers = {"Content-Type": "application/json"}
    if settings.openai_compatible_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_compatible_api_key}"
    try:
        response = requests.post(f"{settings.openai_compatible_base_url}/chat/completions",
            json={"model": model, "messages": messages, "max_tokens": max_tokens}, headers=headers, timeout=(5, 30))
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"], data.get("usage") or {}, str(data.get("model") or model)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError("The configured chat endpoint failed; no fallback was attempted") from None
