import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Button, LinearProgress, Stack, Typography } from "@mui/material";
import ExpandMoreOutlined from "@mui/icons-material/ExpandMoreOutlined";
import { Link } from "react-router-dom";
import { apiJson } from "../../../api/client";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";

import type { BatchProgress } from "../../../api/types";
export type { BatchProgress } from "../../../api/types";

type Range = { file_id?: string; filename?: string; source_relpath?: string; char_start?: number; char_end?: number; batch_id?: string };
type Batch = { id: string; ordinal: number; status: string; source_ranges: Range[] };
type Result = { markdown?: string; citations?: unknown[]; artifacts: { id: string; data: unknown }[]; warnings?: string[] };

function ResultBody({ runId, batch }: { runId: string; batch: Batch }) {
  const query = useQuery({ queryKey: ["scope-batch-result", runId, batch.id], queryFn: () => apiJson<{ result: Result | null }>(`/api/enrichment-jobs/runs/${encodeURIComponent(runId)}/batches/${encodeURIComponent(batch.id)}`) });
  return <Stack spacing={1.5}>
    <Typography fontWeight={650}>Documents and text processed</Typography>
    {batch.source_ranges.map((range, index) => <Typography key={index} variant="body2">
      {range.file_id ? <Link to={`/files/${encodeURIComponent(range.file_id)}`}>{range.filename || range.source_relpath || range.file_id}</Link> : `Derived summary: ${range.batch_id}`}
      {range.char_start !== undefined ? ` · characters ${range.char_start.toLocaleString()}–${range.char_end?.toLocaleString()}` : ""}
    </Typography>)}
    {query.isPending ? <LinearProgress /> : null}
    {query.isError ? <Alert severity="error">Could not load this batch. <Button onClick={() => void query.refetch()}>Retry</Button></Alert> : null}
    {query.data?.result?.markdown !== undefined ? <EnrichmentArtifactView data={{ artifact_type: "wiki_markdown", title: "Batch synthesis", markdown: query.data.result.markdown, citations: query.data.result.citations ?? [] }} /> : null}
    {query.data?.result?.artifacts.map(item => <EnrichmentArtifactView key={item.id} data={item.data} />)}
    {query.data?.result?.warnings?.map((warning, index) => <Alert key={index} severity="warning">{warning}</Alert>)}
    {query.data && !query.data.result ? <Typography>This batch has not finished. Completed batches remain saved if the run is paused or fails.</Typography> : null}
  </Stack>;
}

export function ScopeBatchResults({ runId, progress, title }: { runId: string; progress?: BatchProgress; title?: string }) {
  const [missingCursor, setMissingCursor] = useState(0);
  const [missingPrevious, setMissingPrevious] = useState<number[]>([]);
  const [missing, setMissing] = useState(false);
  const missingQuery = useQuery({ queryKey: ["scope-batch-missing", runId, missingCursor], queryFn: () => apiJson<{items: {file_id: string; filename?: string}[]; next_cursor: number | null}>(`/api/enrichment-jobs/runs/${encodeURIComponent(runId)}/sources?only_missing=true&limit=50&cursor=${missingCursor}`), enabled: missing });
  const [open, setOpen] = useState(false); const [cursor, setCursor] = useState(0);
  const [previous, setPrevious] = useState<number[]>([]);
  const query = useQuery({ queryKey: ["scope-batch-list", runId, cursor, progress?.completed_batches], queryFn: () => apiJson<{ items: Batch[]; next_cursor: number | null }>(`/api/enrichment-jobs/runs/${encodeURIComponent(runId)}/batches?cursor=${cursor}&limit=10`), enabled: open,
    refetchInterval: open && progress && progress.completed_batches < progress.map_batches ? 2500 : false });
  return <Stack spacing={1.5}>
    {title ? <Typography variant="h6">{title}</Typography> : null}
    {progress ? <>
      <Typography>{progress.completed_documents.toLocaleString()} of {progress.documents_with_text.toLocaleString()} documents processed · {progress.completed_batches.toLocaleString()} of {progress.map_batches.toLocaleString()} text batches saved</Typography>
      <LinearProgress aria-label="Full text processing progress" variant="determinate" value={progress.text_characters ? Math.min(100, progress.processed_characters / progress.text_characters * 100) : 0} />
      <Typography variant="caption">{progress.processed_characters.toLocaleString()} / {progress.text_characters.toLocaleString()} saved-text characters · {progress.reduce_batches.toLocaleString()} summary-combination batches saved</Typography>
      {progress.documents_without_text ? <Alert severity="warning">{progress.documents_without_text.toLocaleString()} documents have no usable saved text. Read or extract them before including them in a new run. <Button onClick={() => setMissing(value => !value)}>{missing ? "Hide documents" : "Show documents"}</Button></Alert> : null}
      {progress.reduction === "partitioned" ? <Typography variant="caption">Results are grouped by batch. Rankings or selections made inside a batch are not a global ranking.</Typography> : <Typography variant="caption">The combined summary is built from the saved batch summaries. Original text and each intermediate result remain available.</Typography>}
    </> : null}
    {missing ? <Stack>{missingQuery.isError ? <Alert severity="error">Could not load the skipped documents.</Alert> : null}{missingQuery.data?.items.map(item => <Link key={item.file_id} to={`/files/${encodeURIComponent(item.file_id)}`}>{item.filename ?? item.file_id}</Link>)}<Stack direction="row"><Button disabled={!missingPrevious.length} onClick={() => { setMissingCursor(missingPrevious[missingPrevious.length - 1]); setMissingPrevious(value => value.slice(0, -1)); }}>Previous documents</Button><Button disabled={missingQuery.data?.next_cursor == null} onClick={() => { setMissingPrevious(value => [...value, missingCursor]); setMissingCursor(missingQuery.data!.next_cursor!); }}>Next documents</Button></Stack></Stack> : null}
    <Button sx={{ alignSelf: "start" }} onClick={() => setOpen(value => !value)}>{open ? "Hide batch details" : "View batches and processed documents"}</Button>
    {open ? <>
      {query.isPending ? <LinearProgress /> : null}
      {query.isError ? <Alert severity="error">Could not load batches. <Button onClick={() => void query.refetch()}>Retry</Button></Alert> : null}
      {query.data?.items.map(batch => <Accordion key={batch.id} variant="outlined" disableGutters slotProps={{ transition: { unmountOnExit: true } }}>
        <AccordionSummary expandIcon={<ExpandMoreOutlined />}><Typography>Batch {batch.ordinal + 1} · {batch.status} · {batch.source_ranges.length} text windows</Typography></AccordionSummary>
        <AccordionDetails><ResultBody runId={runId} batch={batch} /></AccordionDetails>
      </Accordion>)}
      <Stack direction="row" spacing={1}>
        <Button disabled={!previous.length} onClick={() => { setCursor(previous[previous.length - 1]); setPrevious(value => value.slice(0, -1)); }}>Previous batches</Button>
        <Button disabled={query.data?.next_cursor == null} onClick={() => { setPrevious(value => [...value, cursor]); setCursor(query.data!.next_cursor!); }}>Next batches</Button>
      </Stack>
    </> : null}
  </Stack>;
}
