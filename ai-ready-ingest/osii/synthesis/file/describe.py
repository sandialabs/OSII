from pathlib import Path
import tomllib

from osii.model_clients import create_shirty_client
from osii.domain.artifacts.synth_artifacts import write_object_synthesis_variant
from osii.domain.read.docs import get_doc_meta
from osii.domain.storage.store import meta_toml_path
from osii.domain.storage.synth import write_object_synth
from osii.synthesis.file.base import BaseSynthesizer, SynthesisState
from osii.synthesis.common import read_concatenated_text
from osii.synthesis.prompts import load_prompt


MODEL = "openai/gpt-oss-120b"


def read_meta(osii_root: Path, file_id: str) -> dict | None:
    path = meta_toml_path(osii_root, file_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _msg_content(msg) -> str:
    if msg is None:
        return ""
    if isinstance(msg, dict):
        return msg.get("content") or ""
    return getattr(msg, "content", None) or ""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _parse_toml_or_fallback(raw: str) -> tuple[dict, bool]:
    cleaned = _strip_code_fences(raw)

    try:
        data = tomllib.loads(cleaned)
        return data, False
    except Exception:
        fallback = {
            "synthesis": {
                "synthesis": (cleaned[:300].strip() if cleaned else "No synthesis generated."),
                "doc_type": "unknown",
                "quality": "low",
            },
            "details": {
                "description": cleaned if cleaned else "The model returned no structured TOML output."
            },
        }
        return fallback, True


class DescribeSynthesizer(BaseSynthesizer):
    name = "describe"
    display_name = "Describe Synthesizer"
    description = (
        "Produces a best-effort description of what an extracted object appears to be, "
        "what it contains, and any caveats in the extracted text."
    )
    version = "1.0"
    scope = "object"
    mode = "description"
    domain = "generic"

    def describe(self) -> dict:
        data = super().describe()
        data["scope"] = self.scope
        data["mode"] = self.mode
        data["domain"] = self.domain
        return data

    def _call_model(self, model: str, system: str, user: str) -> str:
        client = create_shirty_client()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=700,
        )
        msg = completion.choices[0].message if completion and completion.choices else None
        return (_msg_content(msg) or "").strip()

    def synthesize(
        self,
        *,
        osii_store: Path,
        file_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        synthesizer_config = synthesizer_config or {}
        model = synthesizer_config.get("model", MODEL)
        max_chars = int(synthesizer_config.get("max_chars", 12000))

        state = SynthesisState()

        try:
            meta = read_meta(osii_store, file_id)
            raw_text, text_record_count = read_concatenated_text(osii_store, file_id)

            state.text_records_seen = text_record_count
            state.text_chars_read = len(raw_text)

            text = raw_text[:max_chars].strip()
            metadata = meta.get("file", {}) if meta else {}

            system = load_prompt("file", "object_describe_system.txt")
            user_template = load_prompt("file", "object_describe_user.txt")
            user = user_template.format(
                metadata=metadata,
                expert_context=expert_context or "No additional guidance provided.",
                text=text,
            )

            out = self._call_model(model, system, user)
            data, used_fallback = _parse_toml_or_fallback(out)

            if used_fallback:
                state.warnings.append("Object synthesis response was not valid TOML; retrying once with stronger formatting instructions.")
                retry_user = user + "\n\nReturn TOML only. Do not include prose outside TOML. Do not use markdown fences."
                out_retry = self._call_model(model, system, retry_user)
                data, used_fallback = _parse_toml_or_fallback(out_retry)

                if used_fallback:
                    state.warnings.append("Object synthesis retry also failed to return valid TOML; using fallback synthesis structure.")

            synth = data.get("synthesis", {})
            details = data.get("details", {})

            synthesis = (synth.get("synthesis") or "").strip() or "No synthesis generated."
            doc_type = (synth.get("doc_type") or "unknown").strip() or "unknown"
            quality = (synth.get("quality") or "default").strip() or "default"
            description = (details.get("description") or "").strip() or None

            write_object_synth(
                osii_store,
                file_id,
                source_relpath=metadata.get("source_relpath", ""),
                synthesis=synthesis,
                doc_type=doc_type,
                quality=quality,
                description=description,
            )

            write_object_synthesis_variant(
                osii_store,
                file_id,
                method=self.name,
                text=description or synthesis,
                metadata={
                    "method": self.name,
                    "version": self.version,
                    "scope": self.scope,
                    "mode": self.mode,
                    "domain": self.domain,
                    "model": model,
                    "max_chars": max_chars,
                    "expert_context_used": bool(expert_context),
                    "expert_context": expert_context,
                    "source_relpath": metadata.get("source_relpath", ""),
                    "doc_type": doc_type,
                    "quality": quality,
                },
            )

            state.output_chars_written = len(description or synthesis)

        except Exception as exc:
            state.error = str(exc)

        if state.error:
            raise RuntimeError(state.error)

        return {
            "file_id": file_id,
            "synth_rel": f"objects/{file_id}/synth.txt",
            "synth_toml_rel": f"objects/{file_id}/synth.toml",
            "error": None,
        }
