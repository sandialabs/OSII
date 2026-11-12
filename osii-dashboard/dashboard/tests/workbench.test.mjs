import assert from "node:assert/strict";
import test from "node:test";
import { documentTools, workbenchNavigation } from "../src/domain/workbench.ts";
test("home tiles have distinct existing destinations and the requested labels", () => {
 assert.deepEqual(documentTools.map(t=>t.label), ["Browse","Search","Chat","Create a Report","Analyze Library","Explore Topics"]);
 assert.equal(new Set(documentTools.map(t=>t.path)).size,6);
 assert.equal(documentTools.find(t=>t.id==="overview").path,"/library-overview");
 assert.ok(documentTools.every(t=>t.description && t.illustration));
});
test("Home is outside Library and AI workflows belong under Tools", () => {
 assert.deepEqual(workbenchNavigation.filter(t=>t.group==="documents").map(t=>t.label),["Files","Browse","Collections"]);
 assert.deepEqual(workbenchNavigation.filter(t=>t.group==="tools").map(t=>t.label),["Search","Chat","Create a Report","Analyze Library","Explore Topics"]);
 assert.equal(workbenchNavigation[0].path,"/");
 assert.equal(workbenchNavigation.find(t=>t.id==="files").path,"/files");
});
