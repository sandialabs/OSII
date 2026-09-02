from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from osii.expert_context import resolve_expert_context
from typing import List, Tuple

from tqdm import tqdm
from typing import Any

from osii.model_clients import ChatClient, create_chat_client

from osii.domain.storage.synth import write_object_synth
from osii.synthesis.file.base import BaseSynthesizer, SynthesisState
from osii.synthesis.common import ensure_object_synth_dir, read_concatenated_text
from osii.synthesis.prompts import load_prompt

MODEL = "openai/gpt-oss-120b"

# Much larger defaults, appropriate for a large-context model.
# The point is to avoid unnecessary splitting for ordinary documents.
CHUNK_CHAR_TARGET = 60_000
CHUNK_CHAR_HARD_MAX = 80_000
COMBINE_GROUP_SIZE = 8

MAX_TOKENS_CHUNK_synthesis = 900
MAX_TOKENS_COMBINE = 1200

MAX_LINE_LEN_KEEP = 600
MIN_ALPHA_FRAC = 0.20
MIN_VOWEL_FRAC = 0.10

_vowels = set("aeiouAEIOU")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def approx_tokens_from_chars(n_chars: int) -> int:
    return max(1, math.ceil(n_chars / 4))


def is_garbage_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if len(s) > MAX_LINE_LEN_KEEP:
        return True

    alpha = sum(ch.isalpha() for ch in s)
    if alpha == 0:
        return True

    alpha_frac = alpha / max(1, len(s))
    if alpha_frac < MIN_ALPHA_FRAC:
        if s.count(",") >= 3 or s.count("\t") >= 3 or re.search(r"\b\d+\b", s):
            return False
        return True

    alpha_chars = [ch for ch in s if ch.isalpha()]
    if alpha_chars:
        vowel_frac = sum(ch in _vowels for ch in alpha_chars) / len(alpha_chars)
        if vowel_frac < MIN_VOWEL_FRAC:
            return True

    if re.search(r"(.)\1{8,}", s):
        return True

    non_printable = sum((ord(ch) < 32 and ch not in "\t\n\r") for ch in s)
    if non_printable > 0:
        return True

    return False


def clean_text(text: str) -> Tuple[str, dict]:
    original_chars = len(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")

    lines = text.split("\n")
    kept: List[str] = []
    dropped = 0

    for ln in lines:
        if is_garbage_line(ln):
            dropped += 1
            continue
        ln2 = re.sub(r"[ \t]{2,}", " ", ln).strip()
        kept.append(ln2)

    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    stats = {
        "original_chars": original_chars,
        "cleaned_chars": len(cleaned),
        "lines_total": len(lines),
        "lines_kept": len(kept),
        "lines_dropped": dropped,
        "dropped_line_frac": dropped / max(1, len(lines)),
    }
    return cleaned, stats


def split_recursively(
    text: str,
    target: int = CHUNK_CHAR_TARGET,
    hard_max: int = CHUNK_CHAR_HARD_MAX,
) -> List[str]:
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


class RecursiveSynthesizer(BaseSynthesizer):
    name = "recursive"
    display_name = "Recursive Synthesizer"
    description = (
        "Cleans extracted text, splits it only when needed, synthesizes each chunk, "
        "and recursively combines the chunk synthesis into one final synthesis output."
    )
    version = "1.0"
    scope = "object"
    mode = "synthesis"
    domain = "generic"

    def describe(self) -> dict:
        data = super().describe()
        data["scope"] = self.scope
        data["mode"] = self.mode
        data["domain"] = self.domain
        return data

    def synthesize(
        self,
        *,
        osii_store: Path,
        file_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        synthesizer_config = synthesizer_config or {}
        expert_context = resolve_expert_context(osii_store, {"scope_type": "object", "file_id": file_id}, expert_context)
        model = synthesizer_config.get("model", MODEL)
        chunk_char_target = int(synthesizer_config.get("chunk_char_target", CHUNK_CHAR_TARGET))
        chunk_char_hard_max = int(synthesizer_config.get("chunk_char_hard_max", CHUNK_CHAR_HARD_MAX))
        combine_group_size = int(synthesizer_config.get("combine_group_size", COMBINE_GROUP_SIZE))
        max_tokens_chunk_synthesis = int(synthesizer_config.get("max_tokens_chunk_synthesis", MAX_TOKENS_CHUNK_synthesis))
        max_tokens_combine = int(synthesizer_config.get("max_tokens_combine", MAX_TOKENS_COMBINE))

        state = SynthesisState()

        # Keep the working directory if you want to re-enable debug artifact writing later,
        # but do not write to it by default.
        synth_dir = ensure_object_synth_dir(osii_store, file_id) / "synth.recursive"
        synth_dir.mkdir(parents=True, exist_ok=True)

        chunks_dir = synth_dir / "chunks"
        chunk_synthesis_dir = synth_dir / "chunk_synthesis"
        combine_levels_dir = synth_dir / "combine_levels"

        chunks_dir.mkdir(parents=True, exist_ok=True)
        chunk_synthesis_dir.mkdir(parents=True, exist_ok=True)
        combine_levels_dir.mkdir(parents=True, exist_ok=True)

        try:
            raw_text, text_record_count = read_concatenated_text(osii_store, file_id)
            state.text_records_seen = text_record_count
            state.text_chars_read = len(raw_text)

            cleaned, cleaning_stats = clean_text(raw_text)

            # Debug artifacts disabled by default because nested writes have proven brittle
            # in this environment (Windows + OneDrive-backed pathing).
            #
            # If you want to re-enable later, uncomment:
            #
            # write_text(synth_dir / "cleaned_text.txt", cleaned)
            # write_json(synth_dir / "cleaning_stats.json", cleaning_stats)

            chunks = split_recursively(
                cleaned,
                target=chunk_char_target,
                hard_max=chunk_char_hard_max,
            )

            # Debug artifacts disabled by default
            #
            # write_json(
            #     synth_dir / "chunking.json",
            #     {
            #         "chunk_char_target": chunk_char_target,
            #         "chunk_char_hard_max": chunk_char_hard_max,
            #         "num_chunks": len(chunks),
            #         "cleaned_chars": len(cleaned),
            #     },
            # )

            if not chunks:
                state.warnings.append("No text content available for synthesis.")
                final_synthesis = ""
            else:
                client = create_chat_client()
                chunk_synthesis: List[str] = []

                chunk_system_template = load_prompt("object_recursive_chunk_system.txt")
                chunk_user_template = load_prompt("object_recursive_chunk_user.txt")
                combine_system_template = load_prompt("object_recursive_combine_system.txt")
                combine_user_template = load_prompt("object_recursive_combine_user.txt")

                with tqdm(total=len(chunks), desc="Synthesizing chunks", unit="chunk") as pbar:
                    for i, chunk in enumerate(chunks, start=1):
                        # Debug artifacts disabled by default
                        #
                        # write_text(chunks_dir / f"chunk_{i:04d}.txt", chunk)

                        system = chunk_system_template
                        user = chunk_user_template.format(
                            expert_context=expert_context or "No additional guidance provided.",
                            chunk_index=i,
                            chunk_total=len(chunks),
                            chunk=chunk,
                        )

                        t0 = time.time()
                        out, ch, tok_est = chat_complete(
                            client,
                            system=system,
                            user=user,
                            max_tokens=max_tokens_chunk_synthesis,
                        )
                        dt = time.time() - t0

                        out = (out or "").strip()
                        if not out:
                            out = "[EMPTY_MODEL_OUTPUT]"

                        # Debug artifacts disabled by default
                        #
                        # write_text(chunk_synthesis_dir / f"chunk_synthesis_{i:04d}.txt", out)

                        pbar.set_postfix_str(f"consumed~{tok_est}tok ({ch}ch) in {dt:.1f}s")
                        pbar.update(1)

                        chunk_synthesis.append(out)

                level = 1
                current = chunk_synthesis

                while len(current) > 1:
                    group_total = math.ceil(len(current) / combine_group_size)
                    next_level: List[str] = []

                    with tqdm(total=group_total, desc=f"Combining level {level}", unit="group") as pbar:
                        for gi in range(group_total):
                            group = current[gi * combine_group_size:(gi + 1) * combine_group_size]
                            joined = "\n\n".join(f"- Synthesis {i+1}:\n{s}" for i, s in enumerate(group))

                            # Debug artifacts disabled by default -- likely oneDrive issue with long filenames? very strange.
                            #
                            # write_text(
                            #     combine_levels_dir / f"level_{level:02d}_group_{gi+1:04d}_input.txt",
                            #     f"LEVEL {level} GROUP {gi+1}/{group_total}\n\n=== INPUT SYNTHESIS ===\n{joined}\n",
                            # )

                            system = combine_system_template
                            user = combine_user_template.format(
                                expert_context=expert_context or "No additional guidance provided.",
                                level=level,
                                group_index=gi + 1,
                                group_total=group_total,
                                joined=joined,
                            )

                            t0 = time.time()
                            out, ch, tok_est = chat_complete(
                                client,
                                system=system,
                                user=user,
                                max_tokens=max_tokens_combine,
                            )
                            dt = time.time() - t0

                            out = (out or "").strip()
                            if not out:
                                out = "[EMPTY_MODEL_OUTPUT]"

                            # Debug artifacts disabled by default
                            #
                            # write_text(
                            #     combine_levels_dir / f"level_{level:02d}_group_{gi+1:04d}_output.txt",
                            #     out,
                            # )

                            pbar.set_postfix_str(f"consumed~{tok_est}tok ({ch}ch) in {dt:.1f}s")
                            pbar.update(1)

                            next_level.append(out)

                    current = next_level
                    level += 1

                final_synthesis = current[0] if current else ""

            write_object_synth(
                osii_store,
                file_id,
                source_relpath="",
                synthesis=final_synthesis[:400].strip() or "No synthesis generated.",
                doc_type="derived synthesis",
                quality="default",
                description=final_synthesis or None,
            )
            state.output_chars_written = len(final_synthesis)

        except Exception as exc:
            state.error = str(exc)

        if state.error:
            raise RuntimeError(state.error)

        return {
            "file_id": file_id,
            "synth_rel": f"objects/{file_id}/synth.txt",
            "synth_toml_rel": f"objects/{file_id}/synth.toml",
            "artifacts_rel": f"objects/{file_id}/synth.recursive",
            "error": None,
        }
