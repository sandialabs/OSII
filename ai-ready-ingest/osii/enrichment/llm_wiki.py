from __future__ import annotations
import json
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from string import Template
from textwrap import dedent

GENERATED_START = "<!-- LLM_WIKI_GENERATED_START -->"
GENERATED_END = "<!-- LLM_WIKI_GENERATED_END -->"


SAFE_FILE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def validate_file_id(file_id: Any) -> str:
    """
    Validate OSII file IDs before using them in filesystem paths.

    This prevents path traversal such as ../../outside.
    """
    value = str(file_id or "").strip()

    if not SAFE_FILE_ID_RE.fullmatch(value):
        raise ValueError(f"Invalid file_id: {file_id!r}")

    if value in {".", ".."}:
        raise ValueError(f"Invalid file_id: {file_id!r}")

    return value


def ensure_path_within(root: Path, path: Path) -> Path:
    """
    Resolve a path and verify it remains under root.

    Raises ValueError if path escapes root.
    """
    root_resolved = root.resolve()
    path_resolved = path.resolve()

    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"Path escapes expected root: path={path_resolved} root={root_resolved}"
        ) from exc

    return path_resolved


def reject_symlink_path(path: Path) -> None:
    """
    Refuse direct symlink paths.

    This is a basic symlink safety check. It does not fully eliminate TOCTOU
    races, but it prevents common accidental or malicious symlink use.
    """
    if path.exists() and path.is_symlink():
        raise RuntimeError(f"Refusing to use symlink path: {path}")


def reject_symlinks_under(root: Path) -> None:
    """
    Refuse any existing symlinks under a controlled root.
    """
    if not root.exists():
        return

    if root.is_symlink():
        raise RuntimeError(f"Refusing symlink root: {root}")

    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlink under controlled root: {path}")

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


MANUAL_EDIT_FIELD = "manual_edit_utc"


def split_front_matter(text: str) -> tuple[list[str], str]:
    """
    Return the front matter lines and the body below them.

    A page without front matter yields an empty field list and its whole text.
    """
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        return [], text

    try:
        closing = lines.index("---", 1)
    except ValueError:
        return [], text

    return lines[1:closing], "\n".join(lines[closing + 1:])


def has_manual_edit(text: str) -> bool:
    """
    Whether a page was edited by hand and should be left alone.

    Regeneration replaces whole sections, so a page carrying this marker is
    skipped entirely rather than partially rewritten.
    """
    fields, _ = split_front_matter(text)
    return any(line.split(":", 1)[0].strip() == MANUAL_EDIT_FIELD for line in fields)


def stamp_manual_edit(text: str, timestamp: str) -> str:
    """
    Record that a page was hand-edited, adding front matter if it has none.
    """
    stamp = f"{MANUAL_EDIT_FIELD}: {yaml_string(timestamp)}"
    fields, body = split_front_matter(text)

    if not fields and body == text:
        return "\n".join(["---", stamp, "---", "", text.lstrip("\n")])

    kept = [
        line
        for line in fields
        if line.split(":", 1)[0].strip() != MANUAL_EDIT_FIELD
    ]

    return "\n".join(["---", *kept, stamp, "---", body])


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
        if self.wiki_root.exists():
            reject_symlinks_under(self.wiki_root)
        
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
        file_id = validate_file_id(file_id)
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

            # A hand-edited page is authoritative. Refreshing the generated
            # block would silently discard the author's work, so record the
            # skip and leave the file untouched.
            if has_manual_edit(existing):
                self.append_log(
                    action="skip-manual",
                    title=title,
                    details=[
                        f"Source page: `sources/{page_path.name}`",
                        "Page carries `manual_edit_utc`; regeneration was skipped.",
                    ],
                )
                return page_path

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

        # The template is dedented before values are substituted. Interpolating
        # first would defeat dedent: format_data returns multi-line text whose
        # lines start at column 0, which drops the common indent to zero and
        # leaves every other line indented into a Markdown code block.
        template = Template(dedent("""\
            ---
            title: $title_yaml
            kind: source
            status: needs-llm-integration
            source_relpath: $source_relpath_yaml
            file_id: $file_id_yaml
            created_or_refreshed_utc: $created_utc_yaml
            tags:
            - source
            ---

            # $title

            $generated_start

            ## Generated source metadata

            - Source path: `$source_path`
            - Source relative path: `$source_relpath`
            - OSII file ID: `$file_id`
            - OSII object directory: `$object_dir`
            - Extracted text path: `$extracted_text_path`
            - Object synthesis path: `$synth_text_path`
            - Object synthesis TOML path: `$synth_toml_path`
            - Object metadata path: `$meta_toml_path`
            - Object provenance path: `$provenance_toml_path`

            ## Pipeline results

            - Extractor: `textract`
            - Synthesizer: `describe`
            - Extraction error: `$extract_error`
            - Synthesis error: `$synth_error`

            ## Structured synthesis metadata

            - Document type: `$doc_type`
            - Quality: `$quality`
            - Short synthesis: $short_synthesis

            ## Object synthesis

            $synth_text

            ## Raw machine metadata snapshot

            ### `synth.toml`

            ```json
            $synth_toml_data
            ```

            ### `meta.toml`

            ```json
            $meta_toml_data
            ```

            ### `provenance.toml`

            ```json
            $provenance_toml_data
            ```

            $generated_end
            """))

        return template.safe_substitute(
            title_yaml=yaml_string(title),
            source_relpath_yaml=yaml_string(record.source_relpath),
            file_id_yaml=yaml_string(record.file_id),
            created_utc_yaml=yaml_string(utc_now_iso()),
            title=title,
            generated_start=GENERATED_START,
            source_path=record.source_path,
            source_relpath=record.source_relpath,
            file_id=record.file_id,
            object_dir=record.object_dir,
            extracted_text_path=record.extracted_text_path,
            synth_text_path=record.synth_text_path,
            synth_toml_path=record.synth_toml_path,
            provenance_toml_path=record.provenance_toml_path,
            meta_toml_path=record.meta_toml_path,
            extract_error=extract_error,
            synth_error=synth_error,
            doc_type=doc_type,
            quality=quality,
            short_synthesis=short_synthesis or "_Not available._",
            synth_text=synth_text,
            synth_toml_data=self.format_data(synth_toml),
            meta_toml_data=self.format_data(meta_toml),
            provenance_toml_data=self.format_data(provenance_toml),
            generated_end=GENERATED_END,
        )

    def render_default_maintained_source_sections(self) -> str:
        return dedent("""\
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

        task = Template(dedent("""\
            # Integrate source into LLM-wiki: $title

            ## Source page

            - [[$source_page_rel]]

            ## OSII evidence

            - Object directory: `$object_dir`
            - Object synthesis: `$synth_text_path`
            - Object synthesis TOML: `$synth_toml_path`
            - Extracted text: `$extracted_text_path`
            - Metadata: `$meta_toml_path`
            - Provenance: `$provenance_toml_path`

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
            ## [$today] integrate | $title

            - Source page: [[$source_page_rel]]
            - Updated pages:
            - TBD
            - Notes:
            - TBD
            ```
            """)).safe_substitute(
            title=title,
            source_page_rel=source_page_rel,
            object_dir=record.object_dir,
            synth_text_path=record.synth_text_path,
            synth_toml_path=record.synth_toml_path,
            extracted_text_path=record.extracted_text_path,
            meta_toml_path=record.meta_toml_path,
            provenance_toml_path=record.provenance_toml_path,
            today=utc_today(),
        )

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

    def entity_names_in(self, page: Path) -> list[str]:
        """
        Entity names held by a document-level entities page.

        Entities are stored as `### <name>` entries inside one page per
        document, so the catalog reads names out of the page rather than
        listing a file per entity.
        """
        names = []

        for line in read_text_if_exists(page).splitlines():
            if line.startswith("### "):
                name = line[4:].strip()
                if name:
                    names.append(name)

        return names

    def rebuild_index(self) -> None:
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_dir.mkdir(parents=True, exist_ok=True)

        source_pages = sorted(self.sources_dir.rglob("*.md"))
        entity_pages = sorted(self.entities_dir.glob("*.md"))
        concept_pages = sorted(self.concepts_dir.rglob("*.md"))

        lines: list[str] = [
            "# Index",
            "",
            "This is the content-oriented catalog for the LLM-maintained wiki.",
            "",
            "## Sources",
            "",
        ]

        if source_pages:
            for page in source_pages:
                rel = page.relative_to(self.wiki_root).as_posix()
                lines.append(f"- [[{rel}]]")
        else:
            lines.append("_No source pages yet._")

        lines.extend(["", "## Entities", ""])

        entity_entries = []
        for page in entity_pages:
            rel = page.relative_to(self.wiki_root).as_posix()
            for name in self.entity_names_in(page):
                entity_entries.append(f"- [[{rel}#{name}]]")

        lines.extend(entity_entries or ["_No entities yet._"])

        lines.extend(["", "## Concepts", ""])

        if concept_pages:
            for page in concept_pages:
                rel = page.relative_to(self.wiki_root).as_posix()
                lines.append(f"- [[{rel}]]")
        else:
            lines.append("_No concept pages yet._")

        lines.append("")

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
        return dedent("""\
            # LLM Wiki Operating Instructions

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

def __getattr__(name: str):
    """
    Resolve `LlmWikiEnricher` lazily.

    The enricher facade lives in `llm_wiki_stub`, which imports `LlmWiki` from
    this module. Deferring the lookup until attribute access keeps the two
    modules importable in either order.
    """
    if name == "LlmWikiEnricher":
        from osii.enrichment.llm_wiki_stub import LlmWikiStubEnricher

        return LlmWikiStubEnricher

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
