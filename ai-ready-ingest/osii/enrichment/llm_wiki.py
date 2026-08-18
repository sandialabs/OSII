from __future__ import annotations
import json
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from textwrap import dedent

GENERATED_START = "<!-- LLM_WIKI_GENERATED_START -->"
GENERATED_END = "<!-- LLM_WIKI_GENERATED_END -->"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def utc_today() -> str:
    return datetime.now(UTC).date().isoformat()


def yaml_string(value: str) -> str:
    """
    JSON string syntax is valid YAML scalar syntax for simple string values.
    """
    return json.dumps(value or "")


def slugify(value: str, fallback: str = "untitled") -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^\w\s.-]", "", value)
    value = re.sub(r"[\s/\\]+", "-", value)
    value = re.sub(r"-+", "-", value)
    value = value.strip("-._")
    return value or fallback


def relpath_or_name(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.name


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_toml_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@dataclass
class WikiObjectRecord:
    file_id: str
    source_path: Path
    data_root: Path
    osii_root: Path
    source_relpath: str

    @property
    def object_dir(self) -> Path:
        return self.osii_root / "objects" / self.file_id

    @property
    def extracted_text_path(self) -> Path:
        return self.object_dir / "text.txt"

    @property
    def synth_text_path(self) -> Path:
        return self.object_dir / "synth.txt"

    @property
    def synth_toml_path(self) -> Path:
        return self.object_dir / "synth.toml"

    @property
    def meta_toml_path(self) -> Path:
        return self.object_dir / "meta.toml"

    @property
    def provenance_toml_path(self) -> Path:
        return self.object_dir / "provenance.toml"


class LlmWiki:
    """
    Markdown wiki layer over OSII extraction/synthesis outputs.

    This class writes only the wiki markdown layer. It does not modify raw
    source files or OSII machine artifacts.
    """

    def __init__(self, *, wiki_root: Path):
        self.wiki_root = wiki_root.resolve()

        self.sources_dir = self.wiki_root / "sources"
        self.entities_dir = self.wiki_root / "entities"
        self.concepts_dir = self.wiki_root / "concepts"
        self.notes_dir = self.wiki_root / "notes"
        self.tasks_dir = self.wiki_root / "_tasks"
        # self.synthesis_dir = self.wiki_root / "synthesis"
        self.index_path = self.wiki_root / "index.md"
        self.log_path = self.wiki_root / "log.md"
        self.agents_path = self.wiki_root / "AGENTS.md"

    def initialize(self) -> None:
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        # self.synthesis_dir.mkdir(parents=True, exist_ok=True)

        if not self.agents_path.exists():
            self.agents_path.write_text(self.default_agents_md(), encoding="utf-8")

        if not self.log_path.exists():
            self.log_path.write_text("# Log\n\n", encoding="utf-8")

        if not self.index_path.exists():
            self.rebuild_index()

    def make_record(
        self,
        *,
        file_id: str,
        source_path: Path,
        data_root: Path,
        osii_root: Path,
        source_relpath: str | None = None,
    ) -> WikiObjectRecord:
        source_path = source_path.resolve()
        data_root = data_root.resolve()
        osii_root = osii_root.resolve()

        return WikiObjectRecord(
            file_id=file_id,
            source_path=source_path,
            data_root=data_root,
            osii_root=osii_root,
            source_relpath=source_relpath or relpath_or_name(data_root, source_path),
        )

    def source_page_path(self, record: WikiObjectRecord) -> Path:
        stem = Path(record.source_relpath).stem
        slug = slugify(stem, fallback=record.file_id[:12])
        return self.sources_dir / f"{slug}-{record.file_id[:12]}.md"

    def upsert_source_page(
        self,
        *,
        record: WikiObjectRecord,
        extract_result: dict | None = None,
        synth_result: dict | None = None,
    ) -> Path:
        """
        Create or refresh a source wiki page.

        The generated block is replaceable. LLM-maintained sections outside the
        generated block are preserved on refresh.
        """
        self.initialize()

        page_path = self.source_page_path(record)
        title = Path(record.source_relpath).name

        synth_text = read_text_if_exists(record.synth_text_path).strip()
        synth_toml = read_toml_if_exists(record.synth_toml_path)
        meta_toml = read_toml_if_exists(record.meta_toml_path)
        provenance_toml = read_toml_if_exists(record.provenance_toml_path)

        generated = self.render_generated_source_block(
            record=record,
            title=title,
            synth_text=synth_text,
            synth_toml=synth_toml,
            meta_toml=meta_toml,
            provenance_toml=provenance_toml,
            extract_result=extract_result or {},
            synth_result=synth_result or {},
        )

        maintained_default = self.render_default_maintained_source_sections()

        if page_path.exists():
            existing = page_path.read_text(encoding="utf-8", errors="replace")
            new_text = self.replace_generated_block(
                existing=existing,
                generated_block=generated,
                default_tail=maintained_default,
            )
        else:
            new_text = f"{generated}\n\n{maintained_default}"

        page_path.write_text(new_text.rstrip() + "\n", encoding="utf-8")

        self.write_ingest_task(record=record, source_page=page_path)

        self.append_log(
            action="ingest",
            title=title,
            details=[
                f"Source page: `sources/{page_path.name}`",
                f"File ID: `{record.file_id}`",
                f"Source relative path: `{record.source_relpath}`",
                f"Object synthesis: `{record.synth_text_path}`",
            ],
        )

        self.rebuild_index()

        return page_path

    def render_generated_source_block(
        self,
        *,
        record: WikiObjectRecord,
        title: str,
        synth_text: str,
        synth_toml: dict[str, Any],
        meta_toml: dict[str, Any],
        provenance_toml: dict[str, Any],
        extract_result: dict,
        synth_result: dict,
    ) -> str:
        synthesis = synth_toml.get("synthesis", {}) if isinstance(synth_toml, dict) else {}
        details = synth_toml.get("details", {}) if isinstance(synth_toml, dict) else {}

        doc_type = str(synthesis.get("doc_type", "") or "")
        quality = str(synthesis.get("quality", "") or "")
        short_synthesis = str(synthesis.get("synthesis", "") or "")
        description = str(details.get("description", "") or "")

        if not synth_text and description:
            synth_text = description

        if not synth_text and short_synthesis:
            synth_text = short_synthesis

        if not synth_text:
            synth_text = "_No object synthesis was found._"

        extract_error = extract_result.get("error") or ""
        synth_error = synth_result.get("error") or ""

        return dedent(f"""\
                ---
            title: {yaml_string(title)}
            kind: source
            status: needs-llm-integration
            source_relpath: {yaml_string(record.source_relpath)}
            file_id: {yaml_string(record.file_id)}
            created_or_refreshed_utc: {yaml_string(utc_now_iso())}
            tags:
            - source
            ---

            # {title}

            {GENERATED_START}

            ## Generated source metadata

            - Source path: `{record.source_path}`
            - Source relative path: `{record.source_relpath}`
            - OSII file ID: `{record.file_id}`
            - OSII object directory: `{record.object_dir}`
            - Extracted text path: `{record.extracted_text_path}`
            - Object synthesis path: `{record.synth_text_path}`
            - Object synthesis TOML path: `{record.synth_toml_path}`
            - Object metadata path: `{record.meta_toml_path}`
            - Object provenance path: `{record.provenance_toml_path}`

            ## Pipeline results

            - Extractor: `textract`
            - Synthesizer: `describe`
            - Extraction error: `{extract_error}`
            - Synthesis error: `{synth_error}`

            ## Structured synthesis metadata

            - Document type: `{doc_type}`
            - Quality: `{quality}`
            - Short synthesis: {short_synthesis or "_Not available._"}

            ## Object synthesis

            {synth_text}

            ## Raw machine metadata snapshot

            ### `synth.toml`

            ```json
            {self.format_data(synth_toml)}
            ```

            ### `meta.toml`

            ```json
            {self.format_data(meta_toml)}
            ```

            ### `provenance.toml`

            ```json
            {self.format_data(provenance_toml)}
            ```

            {GENERATED_END}
            """)

    def render_default_maintained_source_sections(self) -> str:
        return dedent("""/
                 ## LLM-maintained summary

            > The LLM wiki maintainer should replace this section with a durable summary.

            ## Key claims and facts

            - TBD

            ## Entities to update

            - TBD

            ## Concepts to update

            - TBD

            ## Related wiki pages

            - TBD
                      
            ## Notes
                      
            - TBD

            ## Source-grounded notes

            Use this section for durable notes traceable to this source.
            """)

    def replace_generated_block(
        self,
        *,
        existing: str,
        generated_block: str,
        default_tail: str,
    ) -> str:
        """
        Replace only the generated block if the markers exist.

        If the markers are missing, prepend the generated block and preserve
        existing content below it.
        """
        if GENERATED_START in existing and GENERATED_END in existing:
            before = existing.split(GENERATED_START, 1)[0].rstrip()
            after = existing.split(GENERATED_END, 1)[1].lstrip()

            generated_inner = (
                generated_block
                .split(GENERATED_START, 1)[1]
                .split(GENERATED_END, 1)[0]
            )

            return (
                f"{before}\n\n"
                f"{GENERATED_START}{generated_inner}{GENERATED_END}\n\n"
                f"{after}"
            ).rstrip()

        existing_clean = existing.strip()

        if existing_clean:
            return f"{generated_block}\n\n{existing_clean}"

        return f"{generated_block}\n\n{default_tail}"

    def write_ingest_task(
        self,
        *,
        record: WikiObjectRecord,
        source_page: Path,
    ) -> Path:
        title = Path(record.source_relpath).name
        slug = slugify(Path(record.source_relpath).stem, fallback=record.file_id[:12])
        task_path = self.tasks_dir / f"{utc_today()}-integrate-{slug}-{record.file_id[:12]}.md"

        source_page_rel = source_page.relative_to(self.wiki_root).as_posix()

        if task_path.exists():
            return task_path

        task = dedent(f"""# Integrate source into LLM-wiki: {title}

            ## Source page

            - [[{source_page_rel}]]

            ## OSII evidence

            - Object directory: `{record.object_dir}`
            - Object synthesis: `{record.synth_text_path}`
            - Object synthesis TOML: `{record.synth_toml_path}`
            - Extracted text: `{record.extracted_text_path}`
            - Metadata: `{record.meta_toml_path}`
            - Provenance: `{record.provenance_toml_path}`

            ## Required workflow for LLM maintainer

            1. Read `AGENTS.md`.
            2. Read `index.md`.
            3. Read the source page listed above.
            4. Use the generated object synthesis as the first evidence source.
            5. Inspect extracted text only if the synthesis is insufficient.
            6. Update the source page:
            - `LLM-maintained summary`
            - `Key claims and facts`
            - `Entities to update`
            - `Concepts to update`
            - `Contradictions, caveats, and uncertainty`
            7. Create or update relevant pages under:
            - `entities/`
            - `concepts/`
            - `notes/`
            8. Update `index.md`.
            9. Append a completion note to `log.md`.

            ## Suggested log entry

            ```markdown
            ## [{utc_today()}] integrate | {title}

            - Source page: [[{source_page_rel}]]
            - Updated pages:
            - TBD
            - Notes:
            - TBD
            ```
            """)

        task_path.write_text(task, encoding="utf-8")
        return task_path

    def append_log(
        self,
        *,
        action: str,
        title: str,
        details: list[str] | None = None,
    ) -> None:
        self.initialize()

        details = details or []

        lines = [
            f"## [{utc_today()}] {action} | {title}",
            "",
        ]

        for detail in details:
            lines.append(f"- {detail}")

        lines.extend(["", ""])

        with self.log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def rebuild_index(self) -> None:
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_dir.mkdir(parents=True, exist_ok=True)
        # self.synthesis_dir.mkdir(parents=True, exist_ok=True)

        source_pages = sorted(self.sources_dir.rglob("*.md"))
        entity_pages = sorted(self.entities_dir.rglob("*.md"))
        concept_pages = sorted(self.concepts_dir.rglob("*.md"))
        note_pages = sorted(self.notes_dir.rglob("*.md"))
        # synthesis_pages = sorted(self.synthesis_dir.rglob("*.md"))

        lines: list[str] = [
            "# Index",
            "",
            "This is the content-oriented catalog for the LLM-maintained wiki.",
            "",
            "## Sources",
            "",
        ]

        if source_pages:
            for path in source_pages:
                rel = path.relative_to(self.wiki_root).as_posix()
                lines.append(f"- [[{rel}]]")
        else:
            lines.append("_No source pages yet._")

        lines.extend(["", "## Entities", ""])

        if entity_pages:
            for path in entity_pages:
                rel = path.relative_to(self.wiki_root).as_posix()
                lines.append(f"- [[{rel}]]")
        else:
            lines.append("_No entity pages yet._")

        lines.extend(["", "## Concepts", ""])

        if concept_pages:
            for path in concept_pages:
                rel = path.relative_to(self.wiki_root).as_posix()
                lines.append(f"- [[{rel}]]")
                
        else:
            lines.append("_No concept pages yet._")

        lines.extend(["", "## Notes", ""])

        if note_pages:
            for path in note_pages:
                rel = path.relative_to(self.wiki_root).as_posix()
                lines.append(f"- [[{rel}]]")
        else:
            lines.append("_No notes pages yet._")

        # lines.extend(["", "## Synthesis", ""])

        # if synthesis_pages:
        #     for path in synthesis_pages:
        #         rel = path.relative_to(self.wiki_root).as_posix()
        #         lines.append(f"- [[{rel}]]")
        # else:
        #     lines.append("_No synthesis pages yet._")

        # lines.extend(
        #     [
        #         "",
        #         "## Maintenance",
        #         "",
        #         "- [[AGENTS.md]]",
        #         "- [[log.md]]",
        #         "",
        #     ]
        # )

        lines.extend(
            [
                "",
                "## Lookup and manifests",
                "",
            ]
        )

        manifest_path = self.wiki_root / "manifest.json"
        concept_manifest_path = self.wiki_root / "concept_manifest.md"

        if concept_manifest_path.exists():
            lines.append("- [[concept_manifest.md]]")

        if manifest_path.exists():
            lines.append("- `manifest.json`")

        if not concept_manifest_path.exists() and not manifest_path.exists():
            lines.append("_No manifest files yet._")

        lines.extend(
            [
                "",
                "## Maintenance",
                "",
                "- [[AGENTS.md]]",
                "- [[log.md]]",
                "",
            ]
        )

        self.index_path.write_text("\n".join(lines), encoding="utf-8")

    def format_data(self, data: dict[str, Any]) -> str:
        """
        Human-readable representation of TOML-loaded data.

        We use JSON formatting inside markdown code fences to avoid adding a
        TOML writer dependency.
        """
        if not data:
            return ""
        return json.dumps(data, indent=2, ensure_ascii=False)

    def default_agents_md(self) -> str:
        return dedent("""# LLM Wiki Operating Instructions

        This is an LLM-maintained markdown wiki built from OSII extraction and synthesis outputs.

        ## Layers

        1. Raw sources are immutable.
        2. `.osii/` contains machine-generated extraction and synthesis artifacts.
        3. `wiki/` contains the persistent, LLM-maintained markdown knowledge base.

        The LLM may edit files under `wiki/`.

        The LLM must not edit raw source files.

        The LLM should not edit `.osii/` files unless explicitly instructed.

        ## Current pipeline focus

        This wiki currently uses:

        - Extractor: `textract`
        - Object synthesizer: `describe`

        ## Important OSII object files

        For each object:

        - `.osii/objects/<file_id>/text.txt`
        - `.osii/objects/<file_id>/synth.txt`
        - `.osii/objects/<file_id>/synth.toml`
        - `.osii/objects/<file_id>/meta.toml`
        - `.osii/objects/<file_id>/provenance.toml`

        ## Preferred evidence order

        When maintaining wiki pages, prefer evidence in this order:

        1. Object synthesis TOML: `synth.toml`
        2. Object synthesis text: `synth.txt`
        3. Extracted text: `text.txt`
        4. Raw source file, if readable

        ## Directory structure

        - `sources/` — one page per ingested source.
        - `entities/<source-namespace>/` — source-specific entity pages.
        - `concepts/<source-namespace>/` — source-specific concept pages.
        - `notes/` — user-maintained notes pages, usually one per source namespace.
        - `_tasks/` — generated integration tasks.
        - `index.md` — content-oriented catalog.
        - `log.md` — chronological activity log.

        ## Source page convention

        Each source page has two parts:

        1. A generated block between `LLM_WIKI_GENERATED_START` and `LLM_WIKI_GENERATED_END`.
        2. LLM-maintained sections outside that generated block.

        The generated block may be refreshed by tooling.

        The LLM-maintained sections should preserve durable analysis and cross-links.

        ## Ingest workflow

        When integrating a source page:

        1. Read `index.md`.
        2. Read the relevant `sources/*.md` page.
        3. Use the generated object synthesis as the primary input.
        4. Inspect extracted text if needed.
        5. Update the source page with:
        - summary;
        - key facts;
        - entities;
        - concepts;
        - related pages;
        - caveats.
        6. Create or update relevant `entities/`, `concepts/`, and `notes/` pages.
        7. Update `index.md`.
        8. Append an entry to `log.md`.

        ## Query workflow

        When answering a question:

        1. Read `index.md`.
        2. Read relevant wiki pages.
        3. Answer from the wiki first.
        4. If the answer creates durable knowledge, add or update a page under `synthesis/`.
        5. Append an entry to `log.md` if useful.

        ## Lint workflow

        Periodically check for:

        - source pages still marked `needs-llm-integration`;
        - orphan pages;
        - missing backlinks;
        - duplicate concepts;
        - stale claims;
        - contradictions;
        - important concepts lacking pages.
                      
        ## User-maintained notes

        Pages under `notes/` are user-maintained by default.

        The LLM or tooling may create a notes page if it does not exist and may add missing source grounding links, but it should not overwrite, rewrite, summarize, delete, or reorganize user notes unless explicitly instructed.

        ## Grounding rules

        - Do not invent facts.
        - Prefer claims traceable to source pages or OSII synthesis artifacts.
        - If information is uncertain, mark it as uncertain.
        - If new information contradicts older information, preserve both claims and add a caveat.

        ## Source-specific entity/concept directories

        For each source page, create concepts and entities under a source-specific namespace.

        Example:

        - `sources/paper1-sha256-abc123.md`
        - `entities/paper1-sha256-abc123/*.md`
        - `concepts/paper1-sha256-abc123/*.md`

        This keeps per-source extraction organized and avoids mixing all concepts/entities into one flat directory.
        """)