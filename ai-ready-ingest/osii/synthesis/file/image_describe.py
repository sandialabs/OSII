from pathlib import Path
import tomllib
import base64

from osii.model_clients import create_chat_client

from osii.domain.artifacts.synth_artifacts import write_image_synthesis_variant
from osii.domain.storage.store import meta_toml_path, object_synth_path, object_dir
from osii.domain.storage.synth import write_image_synth
from osii.synthesis.file.base import BaseSynthesizer, SynthesisState
from osii.synthesis.prompts import load_prompt


MODEL = "meta-llama/Llama-4-Scout-17B-16E-Instruct"


def read_meta(osii_root: Path, file_id: str) -> dict | None:
    path = meta_toml_path(osii_root, file_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def read_synth(osii_root: Path, file_id: str) -> dict | None:
    path = object_synth_path(osii_root, file_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


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
                "image_type": "unknown",
                "quality": "low",
            },
            "details": {
                "description": cleaned if cleaned else "The model returned no structured TOML output."
            },
        }
        return fallback, True
    
    
def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".gif":
        return "image/gif"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _image_file_to_data_url(image_path: Path) -> str:
    mime = _guess_mime_type(image_path)
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:{mime};base64,{base64_image}"


class ImageDescribeSynthesizer(BaseSynthesizer):
    name = "image_describe"
    display_name = "Image Describe Synthesizer"
    description = (
        "Produces a best-effort description of an extracted image artifact."
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

    def _call_model(self, model: str, system: str, user: str, image_path: Path) -> str:
        image_data_url = _image_file_to_data_url(image_path)

        return create_chat_client().complete(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        { "type": "text", "text": user},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_data_url
                            },
                        },
                    ],
                }
            ],
            max_tokens=700,
        )
    

    def synthesize(
        self,
        *,
        osii_store: Path,
        file_id: str,
        image: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        synthesizer_config = synthesizer_config or {}
        model = synthesizer_config.get("model", MODEL)
        max_chars = int(synthesizer_config.get("max_chars", 12000))

        state = SynthesisState()

        try:
            meta = read_meta(osii_store, file_id)
            metadata = meta.get("file", {}) if meta else {}
            synth_description = read_synth(osii_store, file_id)
            image_path = object_dir(osii_store, file_id) / "artifacts" / image

            system = load_prompt("file", "image_describe_system.txt")
            user_template = load_prompt("file", "image_describe_user.txt")
            user = user_template.format(
                metadata=metadata,
                expert_context=expert_context or "No additional guidance provided.",
                synthesis=synth_description or "No document description provided."
            )

            out = self._call_model(model, system, user, image_path)
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
            image_type = (synth.get("image_type") or "unknown").strip() or "unknown"
            quality = (synth.get("quality") or "default").strip() or "default"
            description = (details.get("description") or "").strip() or None

            write_image_synth(
                osii_store,
                file_id,
                image,
                source_path=str(image_path),
                synthesis=synthesis,
                image_type=image_type,
                quality=quality,
                description=description,
            )

            write_image_synthesis_variant(
                osii_store,
                file_id,
                image,
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
                    "document_synthesis_used": bool(synth_description),
                    "document_synthesis": synth_description,
                    "source_path": str(image_path),
                    "image_type": image_type,
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
            "synth_rel": f"objects/{file_id}/{image.split('.')[0]}.txt",
            "synth_toml_rel": f"objects/{file_id}/{image.split('.')[0]}.toml",
            "error": None,
        }
