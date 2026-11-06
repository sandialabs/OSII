import { useEffect, useState } from "react";
import { Alert, Button, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { api, type Scope } from "./api";
import { EmbeddingMap } from "../topics/components/DocumentEmbeddingMap";
import type { RelatedDocuments, TopicMap } from "../topics/types";

export function TopicExplorer({ scope, open, onSelect }: { scope: Scope; open: (id: string) => void; onSelect: (id: string) => void }) {
  const [map, setMap] = useState<TopicMap | null>(null);
  const [related, setRelated] = useState<RelatedDocuments | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    setBusy(true); setError(""); setMap(null); setRelated(null); setSelected("");
    void api<TopicMap>("/api/topics/map", "POST", { scope }).then(value => { if (current) setMap(value); }).catch(e => { if (current) setError(e.message); }).finally(() => { if (current) setBusy(false); });
    return () => { current = false; };
  }, [scope, revision]);
  useEffect(() => {
    if (!selected) return;
    let current = true;
    setRelated(null); setError("");
    void api<RelatedDocuments>("/api/topics/related", "POST", { scope, file_id: selected }).then(value => { if (current) setRelated(value); }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [scope, selected]);
  return <Stack spacing={2}>
    <Typography variant="h5">Topic explorer</Typography>
    <Typography color="text.secondary">Explore documents by their existing embeddings. This experimental map uses a 2D PCA projection; related documents are ranked using full document vectors. It makes no model calls.</Typography>
    <Button sx={{ alignSelf: "start" }} disabled={busy} onClick={() => setRevision(value => value + 1)}>Refresh map</Button>
    {busy && <Typography>Projecting documents…</Typography>}{error && <Alert severity="info">{error}</Alert>}
    {map && <><Stack direction="row" spacing={1} flexWrap="wrap"><Chip label={`${map.indexed_count} / ${map.scope_count} indexed`} /><Chip label={`${map.stale_count} stale · ${map.unindexed_count} without compatible embeddings`} /><Chip label={`${map.index.model} · ${map.index.dimensions} dimensions`} /></Stack>
      {map.shown_count < map.indexed_count && <Alert severity="info">Showing the first {map.shown_count} documents in stable ID order. Choose a smaller scope to see more detail. Related-document ranking uses all indexed documents in this scope.</Alert>}
      {!map.points.length ? <Alert severity="info">No compatible embeddings in this scope. Ask a curator to process these documents after an administrator selects an embedding model.</Alert> : <><Typography variant="caption">Projection retains {(map.explained_variance * 100).toFixed(1)}% of the variance in the shown vectors. Proximity is approximate and does not establish a factual relationship.</Typography><EmbeddingMap key={`${map.index.id}:${revision}`} points={map.points} selectedId={selected} relatedIds={new Set(related?.results.map(d => d.file_id) ?? [])} onSelect={setSelected} />
        <TextDocumentList points={map.points} selected={selected} choose={setSelected} />
      </>}
    </>}
    {related && <Paper sx={{ p: 2 }}><Stack spacing={2}><Typography variant="h6">Related to {related.document.filename}</Typography><Stack direction="row" spacing={1}><Button onClick={() => open(related.document.file_id)}>Open document</Button><Button onClick={() => onSelect(related.document.file_id)}>Select for collection</Button></Stack>{!related.results.length && <Typography>No other indexed documents in this scope.</Typography>}{related.results.map(doc => <Stack key={doc.file_id} direction="row" spacing={1} alignItems="center"><Button onClick={() => setSelected(doc.file_id)}>{doc.filename}</Button><Typography variant="caption">Cosine similarity: {doc.similarity.toFixed(3)}</Typography><Button onClick={() => open(doc.file_id)}>Open</Button><Button onClick={() => onSelect(doc.file_id)}>Select for collection</Button></Stack>)}</Stack></Paper>}
  </Stack>;
}

function TextDocumentList({ points, selected, choose }: { points: TopicMap["points"]; selected: string; choose: (id: string) => void }) {
  return <TextField select label="Explore a document" value={points.some(p => p.file_id === selected) ? selected : ""} onChange={e => choose(e.target.value)}><MenuItem value="">Select a document</MenuItem>{points.map(doc => <MenuItem key={doc.file_id} value={doc.file_id}>{doc.source_relpath}</MenuItem>)}</TextField>;
}
