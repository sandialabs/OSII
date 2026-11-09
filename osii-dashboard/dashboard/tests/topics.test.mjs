import test from "node:test";
import assert from "node:assert/strict";
import { topicLabel, topicHoverText } from "../src/features/topics/components/presentation.ts";
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
