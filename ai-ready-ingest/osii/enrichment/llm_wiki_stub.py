from __future__ import annotations

from pathlib import Path

from osii.domain.artifacts.enrichment_artifacts import write_scope_enrichment_variant
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.scopes.scopes import normalize_scope_type
from osii.enrichment.base import BaseEnricher, EnrichmentState


class LlmWikiStubEnricher(BaseEnricher):
    name = "llm_wiki_stub"
    display_name = "Local Wiki Stub Enricher"
    description = "Creates a standard wiki-Markdown artifact without a model dependency."
    version = "1.1"

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        state = EnrichmentState()
        try:
            scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))
            file_ids = list_scope_file_ids(osii_store, scope)
            state.input_objects_seen = len(file_ids)
            title = str((enricher_config or {}).get("title") or "OSII Wiki")
            members = "\n".join(f"- `{file_id}`" for file_id in file_ids)
            markdown = (
                f"# {title}\n\n"
                f"This local baseline describes a **{scope_type}** scope containing "
                f"**{len(file_ids)}** objects.\n\n"
                "## Members\n\n"
                f"{members or '_No members._'}\n"
            )
            result = write_scope_enrichment_variant(
                osii_store,
                scope,
                kind="wiki",
                method=self.name,
                payload={
                    "artifact_type": "wiki_markdown",
                    "title": title,
                    "markdown": markdown,
                    "citations": [],
                },
                metadata={
                    "method": self.name,
                    "version": self.version,
                    "expert_context_used": bool(expert_context),
                },
            )
            state.output_files_written = 2
            return {"ok": True, "result": result, "error": None}
        except Exception as exc:
            state.error = str(exc)
            raise RuntimeError(state.error) from exc
