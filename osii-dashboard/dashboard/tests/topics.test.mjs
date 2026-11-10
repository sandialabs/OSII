import test from "node:test";
import assert from "node:assert/strict";
import { topicLabel, topicHoverText, searchTopicDocuments } from "../src/features/topics/components/presentation.ts";
const doc={file_id:"a",filename:"OPAQUE.pdf",source_relpath:"folder/OPAQUE.pdf",chunk_count:1,document_title:"Garden Guide",
 document_metadata:{schema_version:1,method:"text_llm",title:{value:"Garden Guide"},author:{value:null,qualifier:"Not identified"},date:{value:"circa 1940s",qualifier:"Approximate"}}};
test("map label modes preserve filenames and fall back for unknown titles",()=>{
 assert.equal(topicLabel(doc,"filenames"),"OPAQUE.pdf");assert.equal(topicLabel(doc,"titles"),"Garden Guide");
 assert.equal(topicLabel({...doc,document_title:null},"titles"),"OPAQUE.pdf");
});
test("hover always exposes inferred fields, uncertainty and source identity",()=>{
 const hover=topicHoverText(doc);assert.match(hover,/OPAQUE.pdf/);assert.match(hover,/Author: Unknown — Not identified/);
 assert.match(hover,/Date: circa 1940s — Approximate/);assert.match(hover,/verify against the original/);
});

import { mapPositions,circleMembers,updateSelection } from "../src/features/topics/components/geometry.ts";
test("circle selection follows zoomed and panned positions, including its boundary",()=>{
 const points=[{...doc,x:-1,y:0},{...doc,file_id:"b",x:1,y:0}];
 const positions=mapPositions(points,{x:70,y:-20,zoom:2});const a=positions.get("a"),b=positions.get("b");
 assert.deepEqual(circleMembers(positions,a,0),["a"]);
 assert.deepEqual(circleMembers(positions,a,Math.hypot(b.x-a.x,b.y-a.y)),["a","b"]);
 assert.deepEqual(circleMembers(positions,a,NaN),[]);
});
test("cluster edits reject IDs outside the map and support additive and subtractive review",()=>{
 const allowed=new Set(["a","b"]);
 assert.deepEqual([...updateSelection(new Set(["a"]),["b","outside"],"add",allowed)],["a","b"]);
 assert.deepEqual([...updateSelection(new Set(["a","b"]),["a"],"remove",allowed)],["b"]);
 assert.deepEqual([...updateSelection(new Set(["a"]),["b"],"replace",allowed)],["b"]);
});
test("human corrections and descriptive titles are presented honestly",()=>{
 const human={...doc,document_metadata:{...doc.document_metadata,method:"human",descriptive_title:{value:"Short topic label"}}};
 assert.equal(topicLabel(human,"titles"),"Short topic label");assert.match(topicHoverText(human),/Human-corrected/);
 assert.equal(topicLabel(human,"titles","date"),"circa 1940s");
});

test("search is explicit and scales without making a giant dropdown",()=>{
 const documents=Array.from({length:2000},(_,i)=>({...doc,file_id:String(i)}));
 assert.equal(searchTopicDocuments(documents,"g").length,0);
 assert.equal(searchTopicDocuments(documents,"Garden").length,2000);
 assert.equal(searchTopicDocuments(documents,"Garden").slice(0,50).length,50);
 assert.equal(searchTopicDocuments([doc],"Not identified").length,1);
});


import { detailPointIds, nearestPoint } from "../src/features/topics/components/geometry.ts";
test("twenty thousand points remain selectable while detail work stays screen bounded", () => {
 const points = Array.from({length:20000}, (_,i) => ({...doc,file_id:String(i),x:i%200,y:Math.floor(i/200)}));
 const positions = mapPositions(points,{x:0,y:0,zoom:1});
 assert.equal(positions.size,20000);
 assert.equal(circleMembers(positions,{x:400,y:240},500).length,20000);
 const details=detailPointIds(positions,90);
 assert.ok(details.size < 100);
 assert.ok([...details].some(id=>Number(id)>19500)); // Never just the first N IDs.
 const zoomed=mapPositions(points,{x:-644,y:324,zoom:4});
 assert.notDeepEqual([...detailPointIds(zoomed,90)],[...details]);
 const last=positions.get("19999");
 assert.equal(nearestPoint(positions,last),"19999");
 assert.ok(positions.get("19999")); // Detail culling cannot remove selection targets.
});
