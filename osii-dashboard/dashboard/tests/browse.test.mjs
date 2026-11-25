import assert from "node:assert/strict";
import test from "node:test";
import { folderBreadcrumbs, normalizeFolderPath } from "../src/features/browse/contents.ts";

test("breadcrumbs retain navigable ancestors even without saved folder records", () => {
  assert.deepEqual(folderBreadcrumbs("external/Volumes/Team/reports"), [
    { path: "", label: "Library" },
    { path: "external", label: "Other locations" },
    { path: "external/Volumes", label: "Volumes" },
    { path: "external/Volumes/Team", label: "Team" },
    { path: "external/Volumes/Team/reports", label: "reports" },
  ]);
});

test("Windows separators and dot prefixes use the same folder boundaries", () => {
  assert.equal(normalizeFolderPath(".\\reports\\nested\\"), "reports/nested");
  assert.deepEqual(folderBreadcrumbs(""), [{ path: "", label: "Library" }]);
});
