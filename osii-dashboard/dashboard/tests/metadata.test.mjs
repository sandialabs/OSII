import assert from "node:assert/strict";
import test from "node:test";
import { filterFiles, emptyFileFilters } from "../src/domain/fileFilters.ts";
const files = [
  { fileId: "a", title: "Résumé.PDF", subtitle: "research/2026/Résumé.PDF", sourceFileRelpath: null, mime: "application/pdf", sizeBytes: 2 * 1024 ** 2, modifiedAt: "2026-11-08T23:59:59Z", hasPreferredText: true, hasSynthesis: true, hasEnrichments: false },
  { fileId: "b", title: "notes.txt", subtitle: "misc/notes.txt", mime: "text/plain", sourceFileRelpath: null, sizeBytes: null, modifiedAt: null, hasPreferredText: false, hasSynthesis: false, hasEnrichments: true },
];
const search = overrides => filterFiles(files, { ...emptyFileFilters, ...overrides });
test("metadata search combines case-insensitive words, format, size, date and status", () => {
  assert.deepEqual(search({ query: "RÉSUMÉ research", format: "pdf", minMb: "2", maxMb: "2", after: "2026-11-08", before: "2026-11-08", text: "yes", summary: true }).files.map(f => f.fileId), ["a"]);
});
test("unknown metadata stays visible without filters and is excluded from constrained ranges", () => {
  assert.equal(search({}).files.length, 2);
  assert.equal(search({ minMb: "0" }).files.length, 1);
  assert.equal(search({ after: "2026-11-08" }).files.length, 1);
  assert.deepEqual(search({ text: "no", enrichment: true }).files.map(f => f.fileId), ["b"]);
});
test("invalid ranges give a useful error instead of misleading matches", () => {
  assert.match(search({ minMb: "5", maxMb: "2" }).error, /size range/);
  assert.match(search({ after: "2026-11-09", before: "2026-11-08" }).error, /date range/);
});
