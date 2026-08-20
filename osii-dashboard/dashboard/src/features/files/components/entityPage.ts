// src/features/files/components/entityPage.ts

export type EntitySection = {
  name: string;
  group: string;
  body: string;
  startLine: number;
  endLine: number;
};

const ENTITIES_HEADING = "## Entities";

/**
 * Split a document-level entities page into one section per entity.
 *
 * Entities are stored in a single Markdown page: `## <type>` groups holding
 * `### <name>` entries. The dashboard presents each entry as its own page, so
 * the line range is kept to write an edit back into the same file.
 */
export function parseEntitySections(body: string): EntitySection[] {
  const lines = body.split("\n");
  const start = lines.findIndex((line) => line.trim() === ENTITIES_HEADING);
  if (start === -1) return [];

  const sections: EntitySection[] = [];
  let group = "";
  let current: EntitySection | null = null;

  const close = (endLine: number) => {
    if (!current) return;
    current.endLine = endLine;
    current.body = lines.slice(current.startLine, endLine).join("\n").trim();
    sections.push(current);
    current = null;
  };

  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];

    if (line.startsWith("### ")) {
      close(index);
      current = {
        name: line.slice(4).trim(),
        group,
        body: "",
        startLine: index,
        endLine: lines.length,
      };
      continue;
    }

    if (line.startsWith("## ")) {
      close(index);
      group = line.slice(3).trim();
    }
  }

  close(lines.length);

  return sections;
}

/**
 * Replace one entity's section in the full page text, leaving the rest byte
 * for byte as it was.
 */
export function replaceEntitySection(
  fullText: string,
  section: EntitySection,
  newBody: string,
): string {
  const frontMatterOffset = countFrontMatterLines(fullText);
  const lines = fullText.split("\n");
  const from = frontMatterOffset + section.startLine;
  const to = frontMatterOffset + section.endLine;

  return [
    ...lines.slice(0, from),
    ...newBody.trimEnd().split("\n"),
    "",
    ...lines.slice(to),
  ].join("\n");
}

function countFrontMatterLines(text: string): number {
  const lines = text.split("\n");
  if (lines[0]?.trim() !== "---") return 0;

  const closing = lines.indexOf("---", 1);
  return closing === -1 ? 0 : closing + 1;
}

/**
 * Append a new entity section to the end of the page.
 *
 * New entities go after the existing ones rather than into a type group, so
 * creating one never rewrites a section somebody else is editing.
 */
export function appendEntitySection(fullText: string, newBody: string): string {
  return `${fullText.trimEnd()}\n\n${newBody.trim()}\n`;
}

/** The `### ` heading a draft declares, used to select it after saving. */
export function entityNameInDraft(draft: string): string | null {
  const heading = draft.split("\n").find((line) => line.startsWith("### "));
  return heading ? heading.slice(4).trim() || null : null;
}

/** A short id in the same shape the integrator emits. */
export function newEntityUid(): string {
  const hex = Array.from({ length: 12 }, () =>
    Math.floor(Math.random() * 16).toString(16),
  ).join("");
  return `ent-${hex}`;
}
