from pathlib import Path

from osii.domain.read.folders import get_folder_manifest
from osii.domain.read.segments import list_segments, get_segment_text
from osii.domain.read.synthesis import get_synth_text
from osii.domain.read.folder_synthesis import get_folder_synthesis_text
from osii.domain.storage.synth import write_folder_synth_text
from osii.synthesis.folder.base import BaseFolderSynthesizer, FolderSynthesisState
from osii.synthesis.common import light_clean_text


class FolderFirstNSynthesizer(BaseFolderSynthesizer):
    name = "firstN_folder"
    display_name = "FirstN Folder Synthesizer"
    description = (
        "Builds a simple folder-level synthesis by concatenating child folder syntheses, "
        "child object syntheses, and fallback raw extracted text when needed, then writing "
        "the first N characters after light cleanup."
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

    def _read_child_object_text(self, osii_store: Path, file_id: str) -> tuple[str, bool]:
        text = get_synth_text(osii_store, file_id)
        if text:
            return text, True

        records = list_segments(osii_store, file_id)
        texts = []
        for record in records:
            seg_id = record.get("id", "")
            if seg_id.startswith("seg-"):
                try:
                    seg_num = int(seg_id.removeprefix("seg-"))
                except Exception:
                    continue
                chunk = get_segment_text(osii_store, file_id, seg_num)
                if chunk:
                    texts.append(chunk)

        return "\n\n".join(texts).strip(), False

    def synthesize_folder(
        self,
        *,
        osii_store: Path,
        folder_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        synthesizer_config = synthesizer_config or {}
        max_chars = int(synthesizer_config.get("max_chars", 4000))

        state = FolderSynthesisState()

        try:
            manifest = get_folder_manifest(osii_store, folder_id)
            if manifest is None:
                raise RuntimeError(f"Folder manifest not found: {folder_id}")

            parts = []

            for sub in manifest.get("subfolders", []):
                child_folder_id = sub.get("folder_id")
                if not child_folder_id:
                    continue

                child_text = get_folder_synthesis_text(osii_store, child_folder_id)
                if child_text:
                    parts.append(child_text)
                    state.child_folder_synthesis_seen += 1

            for doc in manifest.get("docs", []):
                file_id = doc.get("file_id")
                if not file_id:
                    continue

                child_text, was_synth = self._read_child_object_text(osii_store, file_id)
                if child_text:
                    parts.append(child_text)
                    if was_synth:
                        state.child_object_synthesis_seen += 1
                    else:
                        state.fallback_text_records_seen += 1

            combined = "\n\n".join(parts).strip()
            state.input_chars_read = len(combined)

            cleaned = light_clean_text(combined)
            output = cleaned[:max_chars].strip()

            if not output:
                state.warnings.append("No usable child synthesis or extracted text found for this folder.")

            write_folder_synth_text(
                osii_store=osii_store,
                folder_id=folder_id,
                text=output,
            )
            state.output_chars_written = len(output)

        except Exception as exc:
            state.error = str(exc)

        if state.error:
            raise RuntimeError(state.error)

        return {
            "folder_id": folder_id,
            "synth_rel": f"folders/folder-{folder_id}.synth.txt",
            "error": None,
        }