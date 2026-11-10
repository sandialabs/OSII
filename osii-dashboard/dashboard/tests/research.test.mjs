import assert from "node:assert/strict";
import test from "node:test";
import { applyReportChanges, exportReport, reportChanges } from "../src/domain/research.ts";

test("proposed edits preserve current text until accepted", () => {
  const before = "# Report\n\nKeep this.\nOld claim.\n\nEnd.\n";
  const after = "# Report\n\nKeep this.\nNew claim.\n\nEnd.\nExtra evidence.\n";
  const changes = reportChanges(before, after);
  assert.equal(changes.length, 2);
  assert.equal(applyReportChanges(before, changes), before);
  changes[0].decision = "accept";
  assert.equal(applyReportChanges(before, changes), before.replace("Old claim.", "New claim."));
  changes[1].decision = "reject";
  assert.equal(applyReportChanges(before, changes).includes("Extra evidence."), false);
  assert.equal(applyReportChanges(before, changes.map(c => ({ ...c, decision: "accept" }))), after);
});

test("diff handles insertion, deletion, repeated lines and newline boundaries", () => {
  const values = ["", "a", "a\n", "a\nb\na\n", "\n\na\n\n", "x\ny\nend", "# Heading\n\n[1](/files/a)\n"];
  for (const before of values) for (const after of values) {
    const changes = reportChanges(before, after);
    assert.equal(applyReportChanges(before, changes), before);
    assert.equal(applyReportChanges(before, changes.map(c => ({ ...c, decision: "accept" }))), after);
  }
});

test("large diffs remain bounded and reviewable", () => {
  const before = "a\n".repeat(800), after = "b\n".repeat(800);
  const changes = reportChanges(before, after);
  assert.equal(changes.length, 1);
  assert.equal(applyReportChanges(before, [{ ...changes[0], decision: "accept" }]), after);
});

test("export keeps equations and carries clickable links and exact evidence", () => {
  const source = { id: "S1", filename: "Study", href: "/files/a?char_start=0&char_end=7", excerpt: "Line 1\nLine 2", char_start: 0, char_end: 7, representation_id: "r1", text_sha256: "abc", page: 3 };
  const output = exportReport({ markdown: `Math $x^2$ [S1](${source.href})`, sources: [source, { ...source, id: "S2", href: "/files/unused" }], warnings: ["Sampled evidence"] }, "https://library.test");
  assert.ok(output.includes("$x^2$"));
  assert.ok(output.includes("](https://library.test/files/a?"));
  assert.ok(output.includes("> Line 1\n> Line 2"));
  assert.ok(output.includes("page 3"));
  assert.ok(output.includes("Text SHA-256: `abc`"));
  assert.ok(!output.includes("### S2"));
});
