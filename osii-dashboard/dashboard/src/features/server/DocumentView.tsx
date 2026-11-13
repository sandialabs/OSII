import { useQuery } from "@tanstack/react-query";
import { ExpandMore } from "@mui/icons-material";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert, Accordion, AccordionDetails, AccordionSummary, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { DocumentWorkspace, type DocumentViewMode, type SavedDocumentPanel } from "../files/components/DocumentWorkspace";
import { GroundedSegmentEditor } from "../files/components/GroundedSegmentEditor";
import { ReportPassage } from "../research/ReportPassage";
import { SuggestedMetadata } from "../files/components/SuggestedMetadata";
import type { DocumentMetadata } from "../../api/documentMetadata";
import { MathpixText } from "../../components/text/MathpixText";
import { EnrichmentArtifactView } from "../files/components/EnrichmentArtifactView";
import { FileSourcePanel } from "../files/components/FileSourcePanel";
import { SplitFileView } from "../files/components/SplitFileView";
import type { ManifestRecord } from "../../api/types";
import { api, type Doc } from "./api";

type Version = { id: string; primary: boolean; created_at: string; segment_count: number; processor: { name: string; version: string } };
type Product = { id: string; kind: string; title: string; types: string[] };

function SavedProduct({ fileId, id }: { fileId: string; id: string }) {
  const [artifactPage,setArtifactPage]=useState(0);
  const result = useQuery({ queryKey: ["objects",fileId,"saved-product",id], queryFn: () => api<{payload:Record<string,unknown>;stale?:boolean}>(`/api/objects/${encodeURIComponent(fileId)}/products/${encodeURIComponent(id)}`) });
  if(result.isPending)return <Typography>Loading saved result…</Typography>;
  if(result.isError)return <Alert severity="warning">{(result.error as Error).message}</Alert>;
  const payload=result.data.payload;
  const response=payload.response as {metadata?:{document_metadata?:DocumentMetadata};warnings?:string[];markdown?:string;artifacts?:{id:string;standard_data?:unknown;json_data?:unknown;text?:string}[]} | undefined;
  const render=(value:unknown) => {
    if(typeof value==='string')return <MathpixText text={value} />;
    if(value && typeof value==='object' && 'text' in value && typeof value.text==='string')return <MathpixText text={value.text} />;
    if(value && typeof value==='object' && 'markdown' in value && typeof value.markdown==='string')return <MathpixText text={value.markdown} />;
    const raw=JSON.stringify(value,null,2) ?? '';
    return raw.length>80000 ? <MathpixText text={raw} mode="plain" controls={false} /> : <EnrichmentArtifactView data={value} />;
  };
  return <Stack spacing={1.5}>
    {result.data.stale&&<Alert severity="warning">This result describes older text. It is kept for comparison.</Alert>}
    <SuggestedMetadata metadata={response?.metadata?.document_metadata}/>
    {(response?.warnings ?? []).slice(0,10).map((warning,index)=><Alert key={index} severity="info">{warning}</Alert>)}
    {(response?.artifacts?.length ?? 0)>20&&<Stack direction="row" spacing={1}><Button disabled={!artifactPage} onClick={()=>setArtifactPage(artifactPage-1)}>Previous data</Button><Button disabled={(artifactPage+1)*20>=(response?.artifacts?.length ?? 0)} onClick={()=>setArtifactPage(artifactPage+1)}>Next data</Button></Stack>}
    {response?.markdown && <MathpixText text={response.markdown} />}
    {response?.artifacts?.slice(artifactPage*20,(artifactPage+1)*20).map(item=><Stack key={item.id}>{render(item.standard_data ?? item.json_data ?? item.text)}</Stack>)}
    {!response && render(payload.data ?? payload.standard_data ?? payload.json_data ?? payload.text ?? payload)}
  </Stack>;
}

export function DocumentView({ doc, close, canEdit = false }: { doc: Doc; close: () => void; canEdit?: boolean }) {
  const [params,setParams]=useSearchParams();
  const requested=params.get('view') || params.get('tab');
  const mode:DocumentViewMode=requested==='source'||requested==='text'?requested:'split';
  const [page,setPage]=useState(Number(params.get('page'))||1);
  const [segment,setSegment]=useState<string|null>(params.get('segment_id'));
  const [editing,setEditing]=useState(false);
  const history=useQuery({queryKey:['objects',doc.file_id,'extraction-catalog'],refetchOnWindowFocus:!editing,queryFn:()=>api<{items:Version[]}>(`/api/objects/${doc.file_id}/extractions/catalog`)});
  const products=useQuery({queryKey:['objects',doc.file_id,'product-catalog'],queryFn:()=>api<{items:Product[]}>(`/api/objects/${doc.file_id}/products/catalog`)});
  const versions=history.data?.items ?? [];
  const selected=versions.find(item=>item.id===params.get('extraction_id')) ?? versions.find(item=>item.primary) ?? versions[0];
  const representation=useQuery({queryKey:['objects',doc.file_id,'canonical-text',selected?.id],queryFn:()=>api<{text:string;segments:ManifestRecord[]}>(`/api/objects/${doc.file_id}/texts/canonical${selected?`?extraction_id=${encodeURIComponent(selected.id)}`:''}`),enabled:history.isSuccess});
  const text=representation.data?.text ?? '', segments=representation.data?.segments ?? [];
  const modeChange=(value:DocumentViewMode)=>{if(!editing || window.confirm('Discard unsaved text edits?')){setEditing(false);const next=new URLSearchParams(params);next.set('view',value);next.delete('tab');setParams(next,{replace:true});}};
  const textControls=<Accordion disableGutters elevation={0} variant="outlined" slotProps={{transition:{unmountOnExit:true}}}>
    <AccordionSummary expandIcon={<ExpandMore />}><Typography variant="body2">Text options</Typography></AccordionSummary>
    <AccordionDetails><TextField select fullWidth disabled={editing} size="small" label="Text version" value={selected?.id ?? ''} onChange={event=>{const next=new URLSearchParams(params);next.set('extraction_id',event.target.value);setParams(next);setPage(1);setSegment(null);}} helperText="Saved older versions are read-only. Choosing one does not change search text.">
      {versions.map(item=><MenuItem key={item.id} value={item.id}>{item.primary?'Current text':item.processor.name} · {new Date(item.created_at).toLocaleString()}</MenuItem>)}
    </TextField></AccordionDetails>
  </Accordion>;
  const panels:SavedDocumentPanel[]=(products.data?.items ?? []).map(item=>({id:item.id,label:item.types?.includes('wiki_markdown')?'Wiki':item.kind==='synthesis'?'Summary':item.title,description:item.kind==='synthesis'?'A short account of the document.':item.types?.includes('wiki_markdown')?'A structured reference organized by topic.':'Saved keywords or other document data.'}));
  if(versions.length)panels.push({id:'versions',label:'Text versions',description:'Compare saved readings of the source.'});
  if(params.has('report_source'))panels.push({id:'citation',label:'Cited passage',description:'Inspect the bounded excerpt linked from a report.'});
  return <article aria-label={`Document ${doc.filename}`}><DocumentWorkspace mode={mode} onMode={modeChange} panels={panels} loading={products.isPending} initialPanel={params.get('tab')==='extractions'?'versions':params.get('tab')==='syntheses'?products.data?.items.find(item=>item.kind==='synthesis')?.id:params.get('tab')==='wiki'?products.data?.items.find(item=>item.types?.includes('wiki_markdown'))?.id:params.get('tab')==='enrichments'?products.data?.items.find(item=>item.kind==='enrichment')?.id:undefined}
    header={<Stack direction="row" alignItems="center" spacing={1}><Button onClick={()=>{if(!editing||window.confirm('Discard unsaved text edits?'))close();}}>← Files</Button><Typography fontWeight={700} title={doc.source_relpath} sx={{overflowWrap:'anywhere'}}>{doc.filename}</Typography></Stack>}
    renderPanel={id=>id==='citation'?<ReportPassage text={text} loading={representation.isPending}/>:id==='versions'?<Stack spacing={1}>{versions.map(item=><Button key={item.id} disabled={editing} onClick={()=>{const next=new URLSearchParams(params);next.set('extraction_id',item.id);setParams(next);}}>{item.primary?'Current text':item.processor.name} · {item.segment_count} segments</Button>)}</Stack>:<SavedProduct key={id} fileId={doc.file_id} id={id}/>}>
    <Stack spacing={1.5}>
      {(history.isError||representation.isError)&&<Alert severity="error">Could not load this text version. Reload to retry.</Alert>}
      {products.isError&&<Alert severity="warning">Saved products could not be loaded. Reading remains available.</Alert>}
      {mode==='source' ? <FileSourcePanel fileId={doc.file_id} mime={doc.media_type ?? null} page={page} onPageChange={setPage} segments={segments}/> : (history.isPending || (representation.isPending && !history.isError)) ? <Typography>Loading document text…</Typography> : <>
        {mode==='split'&&<SplitFileView key={selected?.id} fileId={doc.file_id} mime={doc.media_type ?? null} canonicalText={text} segments={segments} readOnly={!canEdit||!selected?.primary||!representation.data} expectedExtractionId={selected?.id} onEditingChange={setEditing} showEdits={Boolean(selected?.primary)} textControls={textControls} page={page} activeSegmentId={segment} onPageChange={setPage} onJumpToSource={position=>{if(position.page)setPage(position.page);setSegment(position.segmentId ?? null);}}/>}
        {mode==='text'&&<GroundedSegmentEditor key={selected?.id} fileId={doc.file_id} canonicalText={text} segments={segments} readOnly={!canEdit||!selected?.primary||!representation.data} expectedExtractionId={selected?.id} onEditingChange={setEditing} showEdits={Boolean(selected?.primary)} controls={textControls}/>}
      </>}
    </Stack>
  </DocumentWorkspace></article>;
}
