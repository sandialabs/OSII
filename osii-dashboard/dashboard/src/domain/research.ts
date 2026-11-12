export type ReportSource = {
  id: string; file_id: string; filename: string; source_relpath: string;
  representation_id: string; text_sha256: string; char_start: number; char_end: number;
  excerpt: string; page: number | null; segment_id: string | null; href: string;
};
export type ReportScope = { scope_type: "collection"; collection_id: string } | { scope_type: "object"; file_id: string };
export type ReportFormat = "markdown" | "mathpix";
export type ResearchReport = {
  markdown: string; sources: ReportSource[]; warnings: string[]; provider: string;
  model: string | null; documents_in_scope: number; documents_sampled: number; format: ReportFormat;
};
export type ReportDraft = ResearchReport & { scope: ReportScope; prompt: string };
export type Change = { start: number; end: number; before: string; after: string; decision: "pending" | "accept" | "reject" };

/** Line-level LCS with a bounded matrix; offsets always address the immutable base. */
export function reportChanges(before: string, after: string): Change[] {
  if (before === after) return [];
  const a = before.match(/[^\n]*\n|[^\n]+$/g) ?? [];
  const b = after.match(/[^\n]*\n|[^\n]+$/g) ?? [];
  if (a.length * b.length > 500_000) return [{ start: 0, end: before.length, before, after, decision: "pending" }];
  const table = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) for (let j = b.length - 1; j >= 0; j--)
    table[i][j] = a[i] === b[j] ? 1 + table[i + 1][j + 1] : Math.max(table[i + 1][j], table[i][j + 1]);
  const changes: Change[] = [];
  let i = 0, j = 0, offset = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) { offset += a[i++].length; j++; continue; }
    const start = offset;
    let removed = "", added = "";
    while (i < a.length || j < b.length) {
      if (i < a.length && j < b.length && a[i] === b[j]) break;
      if (j < b.length && (i === a.length || table[i][j + 1] >= table[i + 1][j])) added += b[j++];
      else { removed += a[i]; offset += a[i++].length; }
    }
    changes.push({ start, end: offset, before: removed, after: added, decision: "pending" });
  }
  return changes;
}

export function applyReportChanges(base: string, changes: Change[]): string {
  let cursor = 0, result = "";
  for (const change of changes) {
    result += base.slice(cursor, change.start) + (change.decision === "accept" ? change.after : change.before);
    cursor = change.end;
  }
  return result + base.slice(cursor);
}

/** Absolute document links plus portable verbatim evidence travel with exports. */
export function exportReport(report: ResearchReport, origin: string): string {
  let markdown = report.markdown;
  for (const source of report.sources) markdown = markdown.split(`](${source.href})`).join(`](${origin}${source.href})`);
  const used = report.sources.filter(source => report.markdown.includes(`](${source.href})`));
  return markdown + "\n\n## Evidence notes\n\n" + report.warnings.map(warning => `- ${warning}`).join("\n") +
    "\n\n" + used.map(source => `### ${source.id}: ${source.filename.replace(/[\r\n]/g, " ")}\n\n` +
      `[Open passage](${origin}${source.href}) · ${source.page != null ? `page ${source.page} · ` : ""}` +
      `characters ${source.char_start}–${source.char_end} · representation ${source.representation_id}\n\n` +
      `Text SHA-256: \`${source.text_sha256}\`\n\n> ${source.excerpt.split("\n").join("\n> ")}`).join("\n\n") + "\n";
}
