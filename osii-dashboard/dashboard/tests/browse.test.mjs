import assert from "node:assert/strict";
import test from "node:test";
import { compareBrowseFiles, folderName, immediateFiles, immediateFolders, normalizeFolderPath } from "../src/features/browse/contents.ts";

const folder = (path) => ({ path, folder_id: path || "root", label: path || "Root" });
const file = (path) => ({ file_id: path, source_relpath: path });

test("root contains immediate folders and files, not descendants", () => {
  const scopes = ["", "reports", "reports/nested", "data"].map(folder);
  assert.deepEqual(immediateFolders(scopes, folder("")).map((item) => item.path), ["data", "reports"]);
  const files = ["source/root.pdf", "source/reports/report.pdf", "source/reports/nested/table.csv"].map(file);
  assert.deepEqual(immediateFiles(files, "").map((item) => item.file_id), ["source/root.pdf"]);
  assert.deepEqual(immediateFiles(files, "reports").map((item) => item.file_id), ["source/reports/report.pdf"]);
});

test("Windows separators and dot prefixes use the same folder boundaries", () => {
  assert.equal(normalizeFolderPath(".\\reports\\nested\\"), "reports/nested");
  assert.equal(folderName(folder("reports\\nested")), "nested");
  assert.equal(folderName(folder("")), "Root");
  assert.equal(immediateFolders([folder("reports\\nested")], folder("reports/")).length, 1);
  assert.equal(immediateFiles([file("reports\\document.pdf")], "./reports/").length, 1);
  assert.equal(immediateFiles([file("reports-other/document.pdf")], "reports").length, 0);
});

test("source file path is preferred and legacy source paths still work", () => {
  assert.equal(immediateFiles([{ source_file_relpath: "new/a.pdf", source_relpath: "old/a.pdf" }], "new").length, 1);
  assert.equal(immediateFiles([{ source_file_relpath: "", source_relpath: "old/a.pdf" }], "old").length, 1);
  assert.equal(immediateFiles([{ file_id: "unknown" }], "").length, 1);
  assert.equal(immediateFiles([{ file_id: "unknown" }], "some-folder").length, 0);
  assert.equal(immediateFiles([file("my_data/report.pdf")], "").length, 1);
  assert.equal(immediateFiles([file("uploaded_data/report.pdf")], "").length, 1);
});

test("names sort naturally; missing dates and sizes sort last", () => {
  const files = [
    { fileId: "10", title: "Report 10", sizeBytes: null, modifiedAt: null },
    { fileId: "2", title: "report 2", sizeBytes: 40, modifiedAt: "2026-01-02" },
    { fileId: "1", title: "Report 1", sizeBytes: 5, modifiedAt: "invalid" },
  ];
  const ids = (sort) => [...files].sort((a, b) => compareBrowseFiles(a, b, sort)).map((file) => file.fileId);
  assert.deepEqual(ids("name-asc"), ["1", "2", "10"]);
  assert.deepEqual(ids("name-desc"), ["10", "2", "1"]);
  assert.deepEqual(ids("size-desc"), ["2", "1", "10"]);
  assert.deepEqual(ids("modified-desc"), ["2", "1", "10"]);
});
