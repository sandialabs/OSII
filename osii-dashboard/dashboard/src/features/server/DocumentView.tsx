import { useQuery } from "@tanstack/react-query";
import { ExpandMore } from "@mui/icons-material";
import { GroundedSegmentEditor } from "../files/components/GroundedSegmentEditor";
import { ReportPassage } from "../research/ReportPassage";
import { SuggestedMetadata } from "../files/components/SuggestedMetadata";
import type { DocumentMetadata } from "../../api/documentMetadata";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert, Accordion, AccordionDetails, AccordionSummary, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { ProcessingOutputCard } from "../files/components/ProcessingOutputCard";
import { FileDetailTabs, type FileTab } from "../files/components/FileDetailTabs";
import { FileSourcePanel } from "../files/components/FileSourcePanel";
import { SplitFileView } from "../files/components/SplitFileView";
import { ExtractionVersions } from "../files/components/ExtractionVersions";
import { EnrichmentArtifactView } from "../files/components/EnrichmentArtifactView";
import type { ManifestRecord } from "../../api/types";
import { api, type Doc } from "./api";

type SavedResponse = { processor: { display_name: string; name: string; version: string }; markdown?: string; artifacts?: { id: string; kind: string; standard_data?: { artifact_type?: string }; json_data?: unknown; text?: string }[]; metadata?: { model?: string; document_metadata?: DocumentMetadata }; warnings?: string[] };
type Artifact = { stale?: boolean; id: string; kind: string; payload: { response?: SavedResponse; created_at?: string; input_extraction_id?: string; id?: string; standard_data?: unknown; json_data?: unknown; text?: string } };
type Extraction = { id: string; primary: boolean; created_at: string; response: { processor: { name: string; version: string }; segments: { id: string; text: string; source_origin: Record<string, unknown> }[]; artifacts?: { id: string; kind: string; standard_data?: unknown; json_data?: unknown; text?: string }[] } };
export function DocumentView({ doc, close, onProcess, canEdit = false }: { doc: Doc; close: () => void; onProcess?: () => void; canEdit?: boolean }) {
  const [params] = useSearchParams();
  const [tab, setTab] = useState<FileTab>("split");
  const [page, setPage] = useState(Number(params.get("page")) || 1);
  const [segment, setSegment] = useState<string | null>(params.get("segment_id"));
  const [extractions, setExtractions] = useState<Extraction[]>([]);
  const [extractionsLoaded, setExtractionsLoaded] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [variant, setVariant] = useState(params.get("extraction_id") ?? "");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (editing) return; let current = true;
    const refresh = () => Promise.all([api<{ items: Extraction[] }>(`/api/objects/${doc.file_id}/extractions`), api<{ items: Artifact[] }>(`/api/objects/${doc.file_id}/artifacts`)]).then(([history, products]) => { if (current) { setExtractions(previous => JSON.stringify(previous) === JSON.stringify(history.items) ? previous : history.items); setArtifacts(products.items); } }).catch(e => { if (current) setError(e.message); }).finally(() => { if (current) setExtractionsLoaded(true); });
    void refresh(); const timer = window.setInterval(() => void refresh(), 5000);
    return () => { current = false; window.clearInterval(timer); };
  }, [doc.file_id, editing]);
  const selected = extractions.find(item => item.id === variant) ?? extractions.find(item => item.primary) ?? extractions[0];
  const representation = useQuery({ queryKey: ["objects", doc.file_id, "canonical-text", selected?.id],
    queryFn: () => api<{ text: string; segments: ManifestRecord[] }>(`/api/objects/${doc.file_id}/texts/canonical${selected ? `?extraction_id=${encodeURIComponent(selected.id)}` : ""}`), enabled: extractionsLoaded });
  const text = representation.data?.text ?? "";
  const segments = representation.data?.segments ?? [];
  const textControls = <Accordion disableGutters elevation={0} variant="outlined" slotProps={{ transition: { unmountOnExit: true } }}>
    <AccordionSummary expandIcon={<ExpandMore />}><Typography variant="body2">Text options · extraction representation</Typography></AccordionSummary>
    <AccordionDetails><TextField select fullWidth disabled={editing} size="small" label="Extraction representation" value={selected?.id ?? ""}
      onChange={event => { setVariant(event.target.value); setPage(1); setSegment(null); }} helperText="Historical extractions are read-only. Choosing one does not change search text.">
      {extractions.map(item => <MenuItem key={item.id} value={item.id}>{item.response.processor.name} · {new Date(item.created_at).toLocaleString()}{item.primary ? " · Primary" : ""}</MenuItem>)}
    </TextField></AccordionDetails>
  </Accordion>;
  const extractionArtifactIds = new Set(extractions[0]?.response.artifacts?.map(item => item.id) ?? []);
  const products = artifacts.filter(item => !extractionArtifactIds.has(item.payload.id ?? "")).filter(item => {
    if (tab === "syntheses") return item.kind === "synthesis";
    if (tab === "wiki") return item.kind === "enrichment" && item.payload.response?.artifacts?.some(a => a.standard_data?.artifact_type === "wiki_markdown");
    return item.kind === "enrichment";
  });
  return <Stack component="article" aria-label={`Document ${doc.filename}`} spacing={1.5}>
      <Stack direction="row" alignItems="center" spacing={2}><Button onClick={() => { if (!editing || window.confirm("Discard unsaved text edits?")) close(); }}>← Files</Button><Typography variant="h6" title={doc.source_relpath} sx={{ overflowWrap: "anywhere" }}>{doc.filename}</Typography></Stack>
      {error && <Alert severity="error">{error}</Alert>}
      <ReportPassage text={text} loading={!extractionsLoaded} />
      <FileDetailTabs value={tab} onChange={value => { if (!editing || window.confirm("Discard unsaved text edits?")) { setEditing(false); setTab(value); } }} />
      {representation.isError && <Alert severity="error">Could not load this extraction. Reload the page to retry.</Alert>}
      {tab === "text" && <GroundedSegmentEditor key={selected?.id} fileId={doc.file_id} canonicalText={text} segments={segments}
        readOnly={!canEdit || !selected?.primary || !representation.data} expectedExtractionId={selected?.id} onEditingChange={setEditing} showEdits={Boolean(selected?.primary)} controls={textControls} />}
      {tab === "source" && <FileSourcePanel fileId={doc.file_id} mime={doc.media_type ?? null} page={page} onPageChange={setPage} segments={segments} />}
      {tab === "split" && <SplitFileView key={selected?.id} readOnly={!canEdit || !selected?.primary || !representation.data} expectedExtractionId={selected?.id} onEditingChange={setEditing} showEdits={Boolean(selected?.primary)} textControls={textControls} fileId={doc.file_id} mime={doc.media_type ?? null} canonicalText={text} segments={segments} activeSegmentId={segment} page={page} onPageChange={setPage} onJumpToSource={position => { if(position.page) setPage(position.page); setSegment(position.segmentId ?? null); }} />}
      {tab === "extractions" && <><Typography color="text.secondary">Extraction history is preserved in PostgreSQL. Re-extraction is staged through Intake & processing; the latest completed extraction supplies search text.</Typography><ExtractionVersions variants={extractions.map(item => ({ id: item.id, extractor: item.response.processor, primary: item.primary, created_utc: item.created_at, text_chars: item.response.segments.reduce((n,s) => n+s.text.length,0), manifest_records: item.response.segments.length }))}>{version => <Stack spacing={1} sx={{ mt: 1 }}>{extractions.find(item => item.id === version.id)?.response.artifacts?.map(artifact => <EnrichmentArtifactView key={artifact.id} data={artifact.standard_data ?? artifact.json_data ?? artifact.text} />)}</Stack>}</ExtractionVersions>{!extractions.length && <Alert severity="info">No extraction versions are available.</Alert>}</>}
      {["syntheses", "wiki", "enrichments"].includes(tab) && <>
        {onProcess && <Button color="secondary" variant="outlined" onClick={onProcess}>Stage processing for this document</Button>}
        {products.map(item => <ProcessingOutputCard key={item.id} title={item.payload.response?.processor.display_name || item.kind} createdAt={item.payload.created_at} model={item.payload.response?.metadata?.model} stale={item.stale} markdown={item.kind === "synthesis" ? item.payload.response?.markdown : undefined}>
          <SuggestedMetadata metadata={item.payload.response?.metadata?.document_metadata}/><Typography variant="caption" color="text.secondary">Processor {item.payload.response?.processor.name} · v{item.payload.response?.processor.version}</Typography>
          {(item.payload.response?.warnings ?? []).map((warning,index) => <Alert key={index} severity="info">{warning}</Alert>)}
          {item.payload.response?.artifacts?.filter(a => tab !== "wiki" || a.standard_data?.artifact_type === "wiki_markdown").map(artifact => <EnrichmentArtifactView key={artifact.id} data={artifact.standard_data ?? artifact.json_data ?? artifact.text} />)}
        </ProcessingOutputCard>)}
        {!products.length && <Alert severity="info">No {tab} have been saved for this document yet.</Alert>}
      </>}
      <Button color="secondary" component="a" href={`/research?file_id=${encodeURIComponent(doc.file_id)}`}>Write a research report</Button>
      <Button color="secondary" component="a" href={`/api/objects/${doc.file_id}/source`} target="_blank" rel="noopener">Open original source</Button>
  </Stack>;
}
