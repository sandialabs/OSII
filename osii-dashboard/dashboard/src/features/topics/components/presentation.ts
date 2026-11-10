import type { TopicDocument } from "../types";
export type TopicDisplay = "filenames" | "titles" | "thumbnails";
export type LabelField =
  | "auto"
  | "descriptive_title"
  | "title"
  | "author"
  | "date"
  | "agency"
  | "document_type";
export function topicLabel(
  document: TopicDocument,
  display: TopicDisplay,
  field: LabelField = "auto",
): string {
  if (display === "filenames") return document.filename;
  if (field !== "auto")
    return document.document_metadata?.[field]?.value || document.filename;
  return (
    document.document_metadata?.descriptive_title?.value ||
    document.document_title ||
    document.filename
  );
}
export function topicHoverText(document: TopicDocument): string {
  const record = document.document_metadata;
  const lines = [document.filename, document.source_relpath];
  if (record) {
    lines.push(
      record.method === "human"
        ? "Human-corrected metadata"
        : "AI-suggested metadata · verify against the original",
    );
    for (const field of [
      "descriptive_title",
      "title",
      "author",
      "date",
      "agency",
      "document_type",
    ] as const) {
      const suggestion = record[field];
      lines.push(
        `${field.replace(/_/g, " ").replace(/^./, (v) => v.toUpperCase())}: ${suggestion?.value || "Unknown"}${suggestion?.qualifier ? ` — ${suggestion.qualifier}` : ""}`,
      );
    }
  } else if (document.document_title) {
    lines.push(
      `Suggested title: ${document.document_title}${document.title_method === "source_first_line" ? " (first-line heuristic)" : ""}`,
    );
  } else
    lines.push("No metadata suggestions yet; run AI synthesis to add them.");
  return lines.join("\n");
}

export function searchTopicDocuments<T extends TopicDocument>(
  documents: readonly T[],
  query: string,
): T[] {
  const term = query.trim().toLocaleLowerCase();
  if (term.length < 2) return [];
  return documents.filter((document) =>
    [
      document.filename,
      document.source_relpath,
      document.document_title || "",
      ...Object.values(document.document_metadata ?? {}).flatMap((field) =>
        typeof field === "object" && field
          ? [
              String((field as { value?: string }).value ?? ""),
              String((field as { qualifier?: string }).qualifier ?? ""),
            ]
          : [],
      ),
    ].some((value) => value.toLocaleLowerCase().includes(term)),
  );
}
