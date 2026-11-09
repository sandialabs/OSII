import { SuggestedMetadata } from "../files/components/SuggestedMetadata";
import type { DocumentMetadata } from "../../api/documentMetadata";
import { useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Dialog, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from "@mui/material";
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
export function DocumentView({ doc, close, onProcess }: { doc: Doc; close: () => void; onProcess?: () => void }) {
  const [tab, setTab] = useState<FileTab>("split");
  const [page, setPage] = useState(1);
  const [segment, setSegment] = useState<string | null>(null);
  const [extractions, setExtractions] = useState<Extraction[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [variant, setVariant] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { let current = true;
    const refresh = () => Promise.all([api<{ items: Extraction[] }>(`/api/objects/${doc.file_id}/extractions`), api<{ items: Artifact[] }>(`/api/objects/${doc.file_id}/artifacts`)]).then(([history, products]) => { if (current) { setExtractions(history.items); setArtifacts(products.items); } }).catch(e => { if (current) setError(e.message); });
    void refresh(); const timer = window.setInterval(() => void refresh(), 5000);
    return () => { current = false; window.clearInterval(timer); };
  }, [doc.file_id]);
  const selected = extractions.find(item => item.id === variant) ?? extractions[0];
  const { text, segments } = useMemo(() => {
    if (!selected) return { text: doc.text ?? "", segments: [] as ManifestRecord[] };
    let text = ""; const segments: ManifestRecord[] = [];
    for (const [index, item] of selected.response.segments.entries()) {
      if (index) text += "\n";
      const start = text.length; text += item.text;
      segments.push({ id: item.id, kind: "text", path: "", span: { char_start: start, char_end: text.length }, source_origin: item.source_origin });
    }
    return { text, segments };
  }, [selected, doc.text]);
  const extractionArtifactIds = new Set(extractions[0]?.response.artifacts?.map(item => item.id) ?? []);
  const products = artifacts.filter(item => !extractionArtifactIds.has(item.payload.id ?? "")).filter(item => {
    if (tab === "syntheses") return item.kind === "synthesis";
    if (tab === "wiki") return item.kind === "enrichment" && item.payload.response?.artifacts?.some(a => a.standard_data?.artifact_type === "wiki_markdown");
    return item.kind === "enrichment";
  });
  return <Dialog open onClose={close} fullWidth maxWidth="xl"><DialogTitle><Stack direction="row" justifyContent="space-between" spacing={2}><Typography variant="h6">{doc.filename}</Typography><Button color="secondary" onClick={close}>Close document</Button></Stack><Typography variant="caption" color="text.secondary">{doc.source_relpath}</Typography></DialogTitle>
    <DialogContent><Stack spacing={2}>
      {error && <Alert severity="error">{error}</Alert>}
      <FileDetailTabs value={tab} onChange={setTab} />
      {["text", "source", "split"].includes(tab) && extractions.length > 0 && <TextField select size="small" label="Extraction representation" value={selected?.id ?? ""} onChange={e => { setVariant(e.target.value); setPage(1); setSegment(null); }} helperText="Compare preserved extractions. Browsing a version does not change the text used for search.">{extractions.map(item => <MenuItem key={item.id} value={item.id}>{item.response.processor.name} · {new Date(item.created_at).toLocaleString()}{item.primary ? " · Primary" : ""}</MenuItem>)}</TextField>}
      {tab === "text" && <Box component="pre" sx={{ maxHeight: "68vh", overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{text}</Box>}
      {tab === "source" && <FileSourcePanel fileId={doc.file_id} mime={doc.media_type ?? null} page={page} onPageChange={setPage} segments={segments} />}
      {tab === "split" && <SplitFileView readOnly fileId={doc.file_id} mime={doc.media_type ?? null} canonicalText={text} segments={segments} activeSegmentId={segment} page={page} onPageChange={setPage} onJumpToSource={position => { if(position.page) setPage(position.page); setSegment(position.segmentId ?? null); }} />}
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
      <Button color="secondary" component="a" href={`/api/objects/${doc.file_id}/source`} target="_blank" rel="noopener">Open original source</Button>
    </Stack></DialogContent>
  </Dialog>;
}
