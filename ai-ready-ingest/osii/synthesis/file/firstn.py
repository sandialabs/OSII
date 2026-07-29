from pathlib import Path

from osii.synthesis.file.base import BaseSynthesizer, SynthesisState
from osii.synthesis.common import (
    light_clean_text,
    read_concatenated_text,
    write_synth_text,
)


class FirstNSynthesizer(BaseSynthesizer):
    name = "firstN"
    display_name = "FirstN Synthesizer"
    description = (
        "Concatenates extracted text segments, applies light whitespace cleanup, "
        "and writes the first N characters as a simple baseline synthesis output."
    )
    version = "1.0"
    scope = "object"
    mode = "summary"
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
        Synthesizer_config: dict | None = None,
    ) -> dict:
        Synthesizer_config = Synthesizer_config or {}
        max_chars = int(Synthesizer_config.get("max_chars", 4000))

        state = SynthesisState()

        try:
            raw_text, text_record_count = read_concatenated_text(osii_store, file_id)
            state.text_records_seen = text_record_count
            state.text_chars_read = len(raw_text)

            cleaned = light_clean_text(raw_text)
            summary = cleaned[:max_chars].strip()

            if not summary:
                state.warnings.append("No text content available for synthesis.")

            write_synth_text(
                osii_store=osii_store,
                file_id=file_id,
                text=summary,
                synthesizer_name=self.name,
                synthesizer_version=self.version,
                config={"max_chars": max_chars},
                expert_context_used=bool(expert_context),
            )
            state.output_chars_written = len(summary)

        except Exception as exc:
            state.error = str(exc)

        if state.error:
            raise RuntimeError(state.error)

        return {
            "file_id": file_id,
            "synth_rel": f"objects/{file_id}/synth.txt",
            "error": None,
        }