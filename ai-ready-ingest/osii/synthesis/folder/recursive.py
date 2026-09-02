from __future__ import annotations

import json
import math
import time
import tomllib
from pathlib import Path
from osii.expert_context import resolve_expert_context
from typing import List

from tqdm import tqdm
from typing import Any

from osii.model_clients import ChatClient, create_chat_client

from osii.domain.storage.store import folder_overview_path
from osii.domain.storage.synth import write_folder_synth
from osii.synthesis.folder.base import BaseFolderSynthesizer, FolderSynthesisState
from osii.synthesis.prompts import load_prompt


MODEL = "openai/gpt-oss-120b"
CHUNK_CHAR_TARGET = 100_000
CHUNK_CHAR_HARD_MAX = 130_000
COMBINE_GROUP_SIZE = 6
MAX_TOKENS_CHUNK = 700
MAX_TOKENS_COMBINE = 900


def approx_tokens_from_chars(n_chars: int) -> int:
    return max(1, math.ceil(n_chars / 4))


def split_recursively(text: str, target: int = CHUNK_CHAR_TARGET, hard_max: int = CHUNK_CHAR_HARD_MAX) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= hard_max:
        return [text]

    for sep in ("\n\n", "\n", ". ", " "):
        parts = text.split(sep)
        if len(parts) == 1:
            continue

        chunks: List[str] = []
        buf = ""
        joiner = sep

        for p in parts:
            candidate = (buf + joiner + p) if buf else p
            if len(candidate) <= target:
                buf = candidate
            else:
                if buf:
                    chunks.append(buf.strip())
                    buf = p
                else:
                    buf = p

            while len(buf) > hard_max:
                chunks.append(buf[:hard_max].strip())
                buf = buf[hard_max:].strip()

        if buf.strip():
            chunks.append(buf.strip())

        if len(chunks) > 1:
            out: List[str] = []
            for c in chunks:
                if len(c) > hard_max:
                    out.extend(split_recursively(c, target=target, hard_max=hard_max))
                else:
                    out.append(c)
            return out

    return [text[i:i + hard_max].strip() for i in range(0, len(text), hard_max)]


def _msg_content(msg) -> str:
    if msg is None:
        return ""
    if isinstance(msg, dict):
        return msg.get("content") or ""
    return getattr(msg, "content", None) or ""


def chat_complete(client: ChatClient, system: str, user: str, max_tokens: int):
    prompt_chars = len(system) + len(user)
    prompt_tokens_est = approx_tokens_from_chars(prompt_chars)

    output = client.complete(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    return output, prompt_chars, prompt_tokens_est


class FolderRecursiveSynthesizer(BaseFolderSynthesizer):
    name = "recursive_folder"
    display_name = "Recursive Folder Synthesizer"
    description = (
        "Builds a folder-level synthesis by recursively synthesizing a compact folder overview."
    )
    version = "1.0"
    scope = "folder"
    mode = "synthesis"
    domain = "generic"

    def describe(self) -> dict:
        data = super().describe()
        data["scope"] = self.scope
        data["mode"] = self.mode
        data["domain"] = self.domain
        return data

    def synthesize_folder(
        self,
        *,
        osii_store: Path,
        folder_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        synthesizer_config = synthesizer_config or {}
        expert_context = resolve_expert_context(osii_store, {"scope_type": "folder", "folder_id": folder_id}, expert_context)
        chunk_char_target = int(synthesizer_config.get("chunk_char_target", CHUNK_CHAR_TARGET))
        chunk_char_hard_max = int(synthesizer_config.get("chunk_char_hard_max", CHUNK_CHAR_HARD_MAX))
        combine_group_size = int(synthesizer_config.get("combine_group_size", COMBINE_GROUP_SIZE))
        max_tokens_chunk = int(synthesizer_config.get("max_tokens_chunk", MAX_TOKENS_CHUNK))
        max_tokens_combine = int(synthesizer_config.get("max_tokens_combine", MAX_TOKENS_COMBINE))

        state = FolderSynthesisState()

        try:
            overview_path = folder_overview_path(osii_store, folder_id)
            if not overview_path.exists():
                raise RuntimeError(f"Folder overview not found: {overview_path}")

            overview = tomllib.loads(overview_path.read_text(encoding="utf-8"))
            overview_text = json.dumps(overview, indent=2, ensure_ascii=False)
            state.input_chars_read = len(overview_text)

            chunks = split_recursively(overview_text, target=chunk_char_target, hard_max=chunk_char_hard_max)

            if not chunks:
                state.warnings.append("No usable overview content found for this folder.")
                final_text = ""
            else:
                client = create_chat_client()
                system = load_prompt("folder", "folder_describe_system.txt")
                chunk_template = load_prompt("folder_describe_user.txt")

                chunk_synthesis = []

                with tqdm(total=len(chunks), desc="Synthesizing folder chunks", unit="chunk") as pbar:
                    for i, chunk in enumerate(chunks, start=1):
                        user = chunk_template.format(
                            overview=chunk,
                            expert_context=expert_context or "No additional guidance provided.",
                        )

                        t0 = time.time()
                        out, ch, tok_est = chat_complete(client, system, user, max_tokens_chunk)
                        dt = time.time() - t0
                        out = (out or "").strip() or "[EMPTY_MODEL_OUTPUT]"
                        pbar.set_postfix_str(f"consumed~{tok_est}tok ({ch}ch) in {dt:.1f}s")
                        pbar.update(1)
                        chunk_synthesis.append(out)

                current = chunk_synthesis
                while len(current) > 1:
                    group_total = math.ceil(len(current) / combine_group_size)
                    next_level = []

                    with tqdm(total=group_total, desc="Combining folder syntheses", unit="group") as pbar:
                        for gi in range(group_total):
                            group = current[gi * combine_group_size:(gi + 1) * combine_group_size]
                            joined = "\n\n".join(f"- Synthesis {i+1}:\n{s}" for i, s in enumerate(group))

                            system = "You are a careful, concise assistant that consolidates syntheses without adding new facts."
                            user = f"""You will combine multiple partial folder syntheses into one coherent folder synthesis.

GUIDANCE:
{expert_context or "No additional guidance provided."}

INPUT SYNTHESIS:
{joined}

Instructions:
- Combine and deduplicate.
- Preserve important technical content.
- Return only the consolidated synthesis text.
"""
                            t0 = time.time()
                            out, ch, tok_est = chat_complete(client, system, user, max_tokens_combine)
                            dt = time.time() - t0
                            out = (out or "").strip() or "[EMPTY_MODEL_OUTPUT]"
                            pbar.set_postfix_str(f"consumed~{tok_est}tok ({ch}ch) in {dt:.1f}s")
                            pbar.update(1)
                            next_level.append(out)

                    current = next_level

                final_text = current[0] if current else ""

            write_folder_synth(
                osii_store,
                folder_id,
                synthesis=final_text[:400].strip() or "No synthesis generated.",
                kind="folder synthesis",
                quality="default",
                description=final_text or None,
            )
            state.output_chars_written = len(final_text)

        except Exception as exc:
            state.error = str(exc)

        if state.error:
            raise RuntimeError(state.error)

        return {
            "folder_id": folder_id,
            "synth_rel": f"folders/folder-{folder_id}.synth.txt",
            "synth_toml_rel": f"folders/folder-{folder_id}.synth.toml",
            "overview_rel": f"folders/folder-{folder_id}.overview.toml",
            "error": None,
        }
