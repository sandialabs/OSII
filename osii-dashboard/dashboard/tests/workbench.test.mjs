import assert from "node:assert/strict";
import test from "node:test";
import { documentTools, workbenchNavigation } from "../src/domain/workbench.ts";
import { documentProducts } from "../src/domain/documentProducts.ts";
import { ocrSourceTypes, sourceCompatibility } from "../src/domain/fileCompatibility.ts";
import { libraryProducts } from "../src/domain/libraryProducts.ts";
test("home tiles have distinct existing destinations and the requested labels", () => {
 assert.deepEqual(documentTools.map(t=>t.label), ["Browse","Search","Chat","Create a Report","Analyze Library","Create Collections","Explore Topics","OCR Workbench"]);
 assert.equal(new Set(documentTools.map(t=>t.path)).size,8);
 assert.equal(documentTools.find(t=>t.id==="overview").path,"/library-overview");
 assert.ok(documentTools.every(t=>t.description && t.illustration));
});
test("Home is outside Library and AI workflows belong under Tools", () => {
 assert.deepEqual(workbenchNavigation.filter(t=>t.group==="documents").map(t=>t.label),["Files","Browse","Collections"]);
 assert.deepEqual(workbenchNavigation.filter(t=>t.group==="tools").map(t=>t.label),["Search","Chat","Create a Report","Analyze Library","Create Collections","Explore Topics","OCR Workbench"]);
 assert.equal(workbenchNavigation[0].path,"/");
 assert.equal(workbenchNavigation.find(t=>t.id==="files").path,"/files");
});

import { folderGroups, matchingCandidates } from '../src/features/collections/collectionBuilder.ts';
test('collection folder proposals retain every file across a large catalog and separate roots',()=>{
 const docs=Array.from({length:2500},(_,i)=>({file_id:String(i),filename:`file-${i}.txt`,source_relpath:i===0?'root.txt':`${i%2?'one':'two'}/file-${i}.txt`}));
 const groups=folderGroups(docs);
 assert.equal(groups.reduce((sum,group)=>sum+group.documents.length,0),2500);
 assert.equal(groups[0].label,'Root');
 assert.equal(folderGroups([{file_id:'w',filename:'a',source_relpath:'folder\\a.txt'}])[0].path,'folder');
 assert.deepEqual(matchingCandidates(docs,'TWO file-2498').map(doc=>doc.file_id),['2498']);
});


test("every Toolbox workspace declares a scope and uses the shared library products", () => {
  for (const tool of documentTools) {
    assert.ok(tool.scope);
    assert.ok(tool.flow.reads.length);
    for (const key of [...tool.flow.reads, ...tool.flow.writes]) assert.ok(libraryProducts[key]);
  }
  assert.deepEqual(documentTools.find(tool => tool.id === "ocr").flow, {
    reads: ["source", "text"], writes: ["text", "artifacts"],
  });
});

test("OCR accepts declared source types and excludes generic readers", () => {
  const types = ocrSourceTypes({ id: "another.reader", descriptor: { capabilities: {
    file_extensions: [".PDF"], media_types: ["image/*"], output_kinds: ["ocr_text"],
  } } });
  assert.equal(sourceCompatibility({ filename: "scan.PDF" }, types), "supported");
  assert.equal(sourceCompatibility({ filename: "scan.png", mime: "image/png" }, types), "unsupported");
  assert.equal(sourceCompatibility({ filename: ".pdf" }, types), "unsupported");
  assert.equal(sourceCompatibility({ mime: "IMAGE/PNG; x=1" }, { media_types: ["image/*"] }), "supported");
  assert.equal(sourceCompatibility({}, { media_types: ["*/*"] }), "supported");
  assert.equal(sourceCompatibility({ mime: "text/plain" }, { media_types: ["image/*"] }), "unsupported");
  assert.equal(sourceCompatibility({ filename: "scan.pdf" }, {}), "undeclared");
  assert.equal(ocrSourceTypes({ id: "native", capabilities: { file_extensions: [".pdf"] } }), undefined);
  assert.equal(ocrSourceTypes({ id: "unknown", capabilities: { output_kinds: ["ocr_text"] } }), undefined);
  assert.ok(ocrSourceTypes({ id: "local.tesseract-page-ocr" }));
});

test("file products preserve distinct families and binary bundle members", () => {
  const rows = documentProducts([
    { family: "synthesis", filename: "current", title: "Current summary" },
    { family: "enrichment", filename: "run/wiki.md", title: "Wiki", artifact_type: "wiki_markdown" },
  ], [
    { kind: "file", name: "current", relpath: "enrichments/current" },
    { kind: "bundle", name: "run", files: [
      { name: "wiki.md", relpath: "run/wiki.md", is_dir: false },
      { name: "evidence.png", relpath: "run/evidence.png", is_dir: false },
      { name: "wiki.meta.json", relpath: "run/wiki.meta.json", is_dir: false },
    ] },
  ]);
  assert.deepEqual(rows.map(row => row.id), ["enrichment:current", "enrichment:run/wiki.md", "enrichment:run/evidence.png", "synthesis:current"]);
  assert.equal(rows[1].title, "Wiki");
  assert.equal(rows[2].editable, false);
  assert.equal(rows[2].relpath, "run/evidence.png");
});
