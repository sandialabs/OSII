import { useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Dialog, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { FileDetailTabs, type FileTab } from "../files/components/FileDetailTabs";
import { FileSourcePanel } from "../files/components/FileSourcePanel";
import { SplitFileView } from "../files/components/SplitFileView";
import { ExtractionVersions } from "../files/components/ExtractionVersions";
import { EnrichmentArtifactView } from "../files/components/EnrichmentArtifactView";
import type { ManifestRecord } from "../../api/types";
import { api, type Doc } from "./api";

type Artifact = { id: string; kind: string; payload: { id?: string; standard_data?: unknown; json_data?: unknown; text?: string } };
type Extraction = { id: string; primary: boolean; created_at: string; response: { processor: { name: string; version: string }; segments: { id: string; text: string; source_origin: Record<string, unknown> }[]; artifacts?: { id: string; kind: string; standard_data?: unknown; json_data?: unknown; text?: string }[] } };
export function DocumentView({ doc, close }: { doc: Doc; close: () => void }) {
  const [tab, setTab] = useState<FileTab>("split");
  const [page, setPage] = useState(1);
  const [segment, setSegment] = useState<string | null>(null);
  const [extractions, setExtractions] = useState<Extraction[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [variant, setVariant] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { let current = true;
    void Promise.all([api<{ items: Extraction[] }>(`/api/objects/${doc.file_id}/extractions`), api<{ items: Artifact[] }>(`/api/objects/${doc.file_id}/artifacts`)]).then(([history, products]) => { if (current) { setExtractions(history.items); setArtifacts(products.items); } }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
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
  const products = artifacts.filter(item => !extractionArtifactIds.has(item.payload.id ?? "")).filter(item => tab === "syntheses" ? /synth|summary/.test(item.kind) : tab === "wiki" ? /wiki/.test(item.kind) || (item.payload.standard_data as { artifact_type?: string })?.artifact_type === "wiki_markdown" : !/synth|summary|wiki/.test(item.kind));
  return <Dialog open onClose={close} fullWidth maxWidth="xl"><DialogTitle><Stack direction="row" justifyContent="space-between" spacing={2}><Typography variant="h6">{doc.filename}</Typography><Button color="secondary" onClick={close}>Close document</Button></Stack><Typography variant="caption" color="text.secondary">{doc.source_relpath}</Typography></DialogTitle>
    <DialogContent><Stack spacing={2}>
      {error && <Alert severity="error">{error}</Alert>}
      <FileDetailTabs value={tab} onChange={setTab} />
      {["text", "source", "split"].includes(tab) && extractions.length > 0 && <TextField select size="small" label="Extraction representation" value={selected?.id ?? ""} onChange={e => { setVariant(e.target.value); setPage(1); setSegment(null); }} helperText="Compare preserved extractions. Browsing a version does not change the text used for search.">{extractions.map(item => <MenuItem key={item.id} value={item.id}>{item.response.processor.name} · {new Date(item.created_at).toLocaleString()}{item.primary ? " · Primary" : ""}</MenuItem>)}</TextField>}
      {tab === "text" && <Box component="pre" sx={{ maxHeight: "68vh", overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{text}</Box>}
      {tab === "source" && <FileSourcePanel fileId={doc.file_id} mime={doc.media_type ?? null} page={page} onPageChange={setPage} segments={segments} />}
      {tab === "split" && <SplitFileView readOnly fileId={doc.file_id} mime={doc.media_type ?? null} canonicalText={text} segments={segments} activeSegmentId={segment} page={page} onPageChange={setPage} onJumpToSource={position => { if(position.page) setPage(position.page); setSegment(position.segmentId ?? null); }} />}
      {tab === "extractions" && <><Typography color="text.secondary">Extraction history is preserved in PostgreSQL. Re-extraction is staged through Intake & processing; the latest completed extraction supplies search text.</Typography><ExtractionVersions variants={extractions.map(item => ({ id: item.id, extractor: item.response.processor, primary: item.primary, created_utc: item.created_at, text_chars: item.response.segments.reduce((n,s) => n+s.text.length,0), manifest_records: item.response.segments.length }))}>{version => <Stack spacing={1} sx={{ mt: 1 }}>{extractions.find(item => item.id === version.id)?.response.artifacts?.map(artifact => <EnrichmentArtifactView key={artifact.id} data={artifact.standard_data ?? artifact.json_data ?? artifact.text} />)}</Stack>}</ExtractionVersions>{!extractions.length && <Alert severity="info">No extraction versions are available.</Alert>}</>}
      {["syntheses", "wiki", "enrichments"].includes(tab) && <>{products.map(item => <EnrichmentArtifactView key={item.id} data={item.payload.standard_data ?? item.payload.json_data ?? item.payload.text ?? item.payload} />)}{!products.length && <Alert severity="info">No {tab} have been saved for this document. Hosted synthesis and enrichment execution are not yet available.</Alert>}</>}
      <Button color="secondary" component="a" href={`/api/objects/${doc.file_id}/source`} target="_blank" rel="noopener">Open original source</Button>
    </Stack></DialogContent>
  </Dialog>;
}
