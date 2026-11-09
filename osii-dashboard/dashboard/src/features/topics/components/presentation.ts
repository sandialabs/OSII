import type { TopicDocument } from "../types";
export type TopicDisplay = "filenames" | "titles" | "thumbnails";
export function topicLabel(document: TopicDocument, display: TopicDisplay): string {
  return display === "filenames" ? document.filename : document.document_title || document.filename;
}
export function topicHoverText(document: TopicDocument): string {
  const record = document.document_metadata;
  const lines = [document.filename, document.source_relpath];
  if (record) {
    lines.push("AI-suggested metadata · verify against the original");
    for (const field of ["title", "author", "date"] as const) {
      const suggestion = record[field];
      lines.push(`${field[0].toUpperCase() + field.slice(1)}: ${suggestion?.value || "Unknown"}${suggestion?.qualifier ? ` — ${suggestion.qualifier}` : ""}`);
    }
  } else if (document.document_title) {
    lines.push(`Suggested title: ${document.document_title}${document.title_method === "source_first_line" ? " (first-line heuristic)" : ""}`);
  } else lines.push("No metadata suggestions yet; run AI synthesis to add them.");
  return lines.join("\n");
}
