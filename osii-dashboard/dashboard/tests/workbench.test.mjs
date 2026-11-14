import assert from "node:assert/strict";
import test from "node:test";
import { documentTools, workbenchNavigation } from "../src/domain/workbench.ts";
test("home tiles have distinct existing destinations and the requested labels", () => {
 assert.deepEqual(documentTools.map(t=>t.label), ["Browse","Search","Chat","Create a Report","Analyze Library","Create Collections","Explore Topics"]);
 assert.equal(new Set(documentTools.map(t=>t.path)).size,7);
 assert.equal(documentTools.find(t=>t.id==="overview").path,"/library-overview");
 assert.ok(documentTools.every(t=>t.description && t.illustration));
});
test("Home is outside Library and AI workflows belong under Tools", () => {
 assert.deepEqual(workbenchNavigation.filter(t=>t.group==="documents").map(t=>t.label),["Files","Browse","Collections"]);
 assert.deepEqual(workbenchNavigation.filter(t=>t.group==="tools").map(t=>t.label),["Search","Chat","Create a Report","Analyze Library","Create Collections","Explore Topics"]);
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
