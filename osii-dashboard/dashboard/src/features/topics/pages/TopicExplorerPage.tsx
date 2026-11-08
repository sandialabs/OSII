import { useMemo, useState } from "react";
import { Alert, Box, Button, Card, CardContent, Chip, LinearProgress, List, ListItemButton, ListItemText, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import type { ScopeDescribeRequest } from "../../../api/types";
import { listFolderScopes } from "../../../api/scopes";
import { useCollections } from "../../../hooks/useCollections";
import { buildFileRoute } from "../../../utils/routes";
import { EmbeddingMap } from "../components/EmbeddingMap";
import { useRelatedDocuments, useTopicMap } from "../useTopics";

export function TopicExplorerPage() {
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState("");
  const scope = useMemo<ScopeDescribeRequest>(() => {
    const collection = params.get("collection_id"), folder = params.get("folder_id");
    return collection ? { scope_type: "collection", collection_id: collection } : folder ? { scope_type: "folder", folder_id: folder } : { scope_type: "root" };
  }, [params]);
  const selectedId = params.get("file_id") ?? "";
  const collections = useCollections();
  const folders = useQuery({ queryKey: ["scopes", "folders"], queryFn: listFolderScopes });
  const map = useTopicMap(scope);
  const related = useRelatedDocuments(scope, selectedId, map.data?.index.id);
  const data = map.data;
  const points = data?.points ?? [];
  const visible = points.filter(p => p.source_relpath.toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  const relatedIds = new Set(related.data?.results.map(p => p.file_id));
  const selected = related.data?.document ?? points.find(p => p.file_id === selectedId);
  const select = (id: string) => { const next = new URLSearchParams(params); next.set("file_id", id); setParams(next); };
  const scopeValue = scope.scope_type === "collection" ? `collection:${scope.collection_id}` : scope.scope_type === "folder" ? `folder:${scope.folder_id}` : "root";
  const knownScope = scopeValue === "root" || collections.data?.collections.some(c => scopeValue === `collection:${c.id}`) || folders.data?.scopes.some(f => scopeValue === `folder:${f.folder_id}`);

  return <Stack spacing={2.5}>
    <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
      <Box><Typography variant="h5" fontWeight={700}>Topic explorer</Typography>
        <Typography color="text.secondary">Explore document content and follow connections through your library.</Typography></Box>
      <Button variant="outlined" disabled={map.isFetching} onClick={() => { void map.refetch(); if (selectedId) void related.refetch(); }}>Refresh</Button>
    </Stack>
    <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
      <TextField select size="small" label="Explore scope" value={scopeValue} sx={{ minWidth: 260 }} onChange={event => {
        const value = event.target.value;
        setFilter("");
        setParams(value === "root" ? {} : value.startsWith("collection:") ? { collection_id: value.slice(11) } : { folder_id: value.slice(7) });
      }}>
        <MenuItem value="root">All documents</MenuItem>
        {(collections.data?.collections ?? []).map(c => <MenuItem key={c.id} value={`collection:${c.id}`}>Collection: {c.name}</MenuItem>)}
        {(folders.data?.scopes ?? []).map(f => <MenuItem key={f.folder_id} value={`folder:${f.folder_id}`}>Folder: {f.path || "/"}</MenuItem>)}
        {!knownScope && <MenuItem value={scopeValue}>Selected scope (unavailable)</MenuItem>}
      </TextField>
      <TextField size="small" label="Filter mapped documents by name or path" value={filter} onChange={event => setFilter(event.target.value)} fullWidth />
    </Stack>
    {(collections.isError || folders.isError) && <Alert severity="warning">Some scopes could not be loaded. Refresh the page to retry.</Alert>}
    {map.isFetching && <LinearProgress aria-label="Loading embedding map" />}
    {map.isError && <Alert severity="warning">{map.error.message} <Link to="/intake">Open Intake</Link> to build embeddings; use <Link to="/admin/processors">Setup</Link> to choose an embedding model.</Alert>}
    {data && !map.isError && <>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip label={`${data.shown_count} of ${data.indexed_count} indexed documents mapped`} />
        <Chip label={`${data.index.model} · ${data.index.dimensions} dimensions`} variant="outlined" />
        <Chip label={`${Math.round(data.explained_variance * 100)}% of variation in 2D`} variant="outlined" />
      </Stack>
      {!data.index.semantic && <Alert severity="info">This index uses lexical or unverified embeddings, not a confirmed semantic model. Connections may reflect shared words rather than meaning.</Alert>}
      {(data.unindexed_count > 0 || data.stale_count > 0) && <Alert severity="info">{data.unindexed_count} documents have no usable embeddings; {data.stale_count} have stale embeddings and are excluded. Rebuild embeddings in Intake to include them.</Alert>}
      {data.indexed_count > data.shown_count && <Alert severity="info">The map shows a stable subset of {data.shown_count} documents. Related results search all {data.indexed_count} indexed documents in this scope. Narrow the scope to see more detail.</Alert>}
      {!points.length ? <Alert severity="info">No documents with current embeddings in this scope. Build embeddings in Intake or select another scope.</Alert> : <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1.7fr) minmax(300px, 1fr)" }, gap: 2 }}>
        <Card><CardContent>
          <EmbeddingMap key={JSON.stringify(scope)} points={visible} selectedId={selectedId} relatedIds={relatedIds} onSelect={select} />
          <Typography variant="subtitle2" sx={{ mt: 2 }}>Mapped documents ({visible.length})</Typography>
          <List dense aria-label="Mapped documents" sx={{ maxHeight: 260, overflow: "auto" }}>
            {visible.map(p => <ListItemButton key={p.file_id} selected={p.file_id === selectedId} onClick={() => select(p.file_id)}>
              <ListItemText primary={p.document_title || p.filename} secondary={p.source_relpath} sx={{ overflowWrap: "anywhere" }} />
            </ListItemButton>)}
          </List>
          {!visible.length && <Typography color="text.secondary">No mapped documents match this filter.</Typography>}
        </CardContent></Card>
        <Card><CardContent><Stack spacing={2}>
          <Typography variant="h6">Related documents</Typography>
          {!selectedId && <Typography color="text.secondary">Select a point or a document from the list to find related content.</Typography>}
          {selected && <Box><Typography fontWeight={700} sx={{ overflowWrap: "anywhere" }}>{selected.document_title || selected.filename}</Typography>
            <Typography variant="caption" color="text.secondary">{selected.chunk_count} indexed chunk{selected.chunk_count === 1 ? "" : "s"} · {selected.source_relpath}</Typography>
            <Box sx={{ mt: 1 }}><Button component={Link} to={buildFileRoute({ fileId: selected.file_id })} size="small">Open document</Button></Box></Box>}
          {related.isFetching && <LinearProgress aria-label="Finding related documents" />}
          {related.isError && <Alert severity="warning">{related.error.message}</Alert>}
          {related.data && !related.isError && <>
            {related.data.index.id !== data.index.id && <Alert severity="info">The index has changed. Refresh the map to align it with these results.</Alert>}
            <Typography variant="caption" color="text.secondary">Ranked by cosine similarity of document embeddings. Scores are similarity, not confidence or proof of a shared topic.</Typography>
            {!related.data.results.length && <Typography>No other indexed documents in this scope.</Typography>}
            {related.data.results.map(p => <Box key={p.file_id} sx={{ borderTop: "1px solid", borderColor: "divider", pt: 1.5 }}>
              <Stack direction="row" spacing={1} justifyContent="space-between"><Typography fontWeight={600} sx={{ overflowWrap: "anywhere" }}>{p.document_title || p.filename}</Typography><Chip size="small" label={p.similarity.toFixed(3)} /></Stack>
              <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{p.source_relpath}</Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}><Button size="small" onClick={() => select(p.file_id)}>Explore related</Button><Button component={Link} to={buildFileRoute({ fileId: p.file_id })} size="small">Open</Button></Stack>
            </Box>)}
          </>}
        </Stack></CardContent></Card>
      </Box>}
      <Typography variant="caption" color="text.secondary">Each point averages a document’s normalized chunk vectors, then normalizes that average. PCA compresses these vectors into two dimensions; axes are not topic labels. No model calls or document changes occur here.</Typography>
    </>}
  </Stack>;
}
