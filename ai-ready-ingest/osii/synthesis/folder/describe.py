from pathlib import Path
import tomllib

from osii.model_clients import create_shirty_client

from osii.domain.artifacts.folder_overview import build_folder_overview
from osii.domain.artifacts.synth_artifacts import write_folder_synthesis_variant
from osii.domain.storage.synth import write_folder_synth
from osii.synthesis.folder.base import BaseFolderSynthesizer, FolderSynthesisState
from osii.synthesis.prompts import load_prompt


MODEL = "openai/gpt-oss-120b"


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
                "kind": "folder",
                "quality": "low",
            },
            "details": {
                "description": cleaned if cleaned else "The model returned no structured TOML output."
            },
        }
        return fallback, True


class FolderDescribeSynthesizer(BaseFolderSynthesizer):
    name = "describe_folder"
    display_name = "Describe Folder Synthesizer"
    description = (
        "Produces a qualitative description of what a folder appears to represent, "
        "what kinds of files it contains, and what a user should inspect next."
    )
    version = "1.0"
    scope = "folder"
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

    def synthesize_folder(
        self,
        *,
        osii_store: Path,
        folder_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        synthesizer_config = synthesizer_config or {}
        model = synthesizer_config.get("model", MODEL)

        state = FolderSynthesisState()

        try:
            overview = build_folder_overview(osii_store, folder_id)

            system = load_prompt("folder", "folder_describe_system.txt")
            user_template = load_prompt("folder", "folder_describe_user.txt")
            user = user_template.format(
                overview=overview,
                expert_context=expert_context or "No additional guidance provided.",
            )

            out = self._call_model(model, system, user)
            data, used_fallback = _parse_toml_or_fallback(out)

            if used_fallback:
                state.warnings.append("Folder synthesis response was not valid TOML; retrying once with stronger formatting instructions.")
                retry_user = user + "\n\nReturn TOML only. Do not include prose outside TOML. Do not use markdown fences."
                out_retry = self._call_model(model, system, retry_user)
                data, used_fallback = _parse_toml_or_fallback(out_retry)

                if used_fallback:
                    state.warnings.append("Folder synthesis retry also failed to return valid TOML; using fallback synthesis structure.")

            synth = data.get("synthesis", {})
            details = data.get("details", {})

            synthesis = (synth.get("synthesis") or "").strip() or "No synthesis generated."
            kind = (synth.get("kind") or "folder").strip() or "folder"
            quality = (synth.get("quality") or "default").strip() or "default"
            description = (details.get("description") or "").strip() or None

            write_folder_synth(
                osii_store,
                folder_id,
                synthesis=synthesis,
                kind=kind,
                quality=quality,
                description=description,
            )

            write_folder_synthesis_variant(
                osii_store,
                folder_id,
                method=self.name,
                text=description or synthesis,
                metadata={
                    "method": self.name,
                    "version": self.version,
                    "scope": self.scope,
                    "mode": self.mode,
                    "domain": self.domain,
                    "model": model,
                    "expert_context_used": bool(expert_context),
                    "expert_context": expert_context,
                    "kind": kind,
                    "quality": quality,
                },
            )

            state.output_chars_written = len(description or synthesis)

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
