import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, LinearProgress, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import type { ProcessingRun } from "../../../api/types";
import { getRunSources } from "../../../api/queue";
import { processingStatus, recordedFileStages } from "../../../domain/processingRun";

const PAGE_SIZE = 25;

export function RunFiles({ run }: { run: ProcessingRun }) {
  const [cursor, setCursor] = useState(0);
  const scoped = run.workflow === "tool";
  const batch = scoped && Boolean(run.batch_progress);
  const sources = useQuery({
    queryKey: ["processing-runs", "detail", run.id, "sources", cursor],
    queryFn: ({ signal }) => getRunSources(run.id, cursor, signal),
    enabled: batch,
  });
  const indexingFiles = useMemo(() => new Set(run.indexing_file_ids), [run.indexing_file_ids]);
  const items = run.items ?? [];
  const memberIds = run.input_summary?.member_ids ?? [];
  const total = batch ? run.batch_progress?.documents ?? 0 : scoped ? memberIds.length : items.length;
  const next = batch ? sources.data?.next_cursor : cursor + PAGE_SIZE < total ? cursor + PAGE_SIZE : null;
  const rows = batch ? (sources.data?.items ?? []).map(item => ({
    label: item.filename || item.file_id, path: item.source_relpath, stages: [],
    status: item.has_text ? "Text available at submission" : "Skipped · no saved text", note: undefined,
  })) : scoped ? memberIds.slice(cursor, cursor + PAGE_SIZE).map(fileId => ({
    label: fileId, path: undefined, stages: [], status: "Included", note: undefined,
  })) : items.slice(cursor, cursor + PAGE_SIZE).map(item => ({
    label: item.display, path: item.source_relpath ?? item.path, stages: recordedFileStages(run, item, indexingFiles),
    status: processingStatus(item.status), note: item.note,
  }));

  return (
    <Paper component="section" variant="outlined" aria-labelledby="run-files" sx={{ p: 2 }}>
      <Stack spacing={1}>
        <Typography id="run-files" component="h2" variant="h6">Files{total > 0 ? ` (${total.toLocaleString()})` : ""}</Typography>
        {batch && sources.isPending && <LinearProgress aria-label="Loading run files" />}
        {sources.isError && <Alert severity="warning" action={<Button onClick={() => void sources.refetch()}>Retry</Button>}>Could not load the saved file list.</Alert>}
        {!total && !batch && <Typography color="text.secondary">No file list was recorded for this run.</Typography>}
        {rows.length > 0 && (
          <TableContainer>
            <Table size="small" aria-label="Files and processors" sx={{ tableLayout: "fixed", "& td": { overflowWrap: "anywhere" } }}>
              <TableHead><TableRow><TableCell sx={{ width: "38%" }}>File</TableCell><TableCell>Status</TableCell>{!scoped && <TableCell>Steps</TableCell>}</TableRow></TableHead>
              <TableBody>{rows.map((row, index) => (
                <TableRow key={cursor + index}>
                  <TableCell>
                    <Typography variant="body2" fontWeight={650}>{row.label}</Typography>
                    {row.path && row.path !== row.label && <Typography variant="caption" color="text.secondary">{row.path}</Typography>}
                  </TableCell>
                  <TableCell>
                    {row.status}
                    {row.note && <Typography variant="body2" color="text.secondary">{row.note}</Typography>}
                  </TableCell>
                  {!scoped && <TableCell>
                    {row.stages.map(stage => (
                      <Typography key={stage.label} variant="body2">
                        {stage.label} · {processingStatus(stage.status)}
                        {stage.processor && !["skipped", "reused"].includes(stage.status) ? ` · ${stage.processor}` : ""}
                      </Typography>
                    ))}
                    {!row.stages.length && <Typography variant="body2" color="text.secondary">No steps recorded</Typography>}
                  </TableCell>}
                </TableRow>
              ))}</TableBody>
            </Table>
          </TableContainer>
        )}
        {(cursor > 0 || next != null) && (
          <Stack direction="row" spacing={1}>
            <Button disabled={cursor === 0} onClick={() => setCursor(Math.max(0, cursor - PAGE_SIZE))}>Previous files</Button>
            <Button disabled={next == null} onClick={() => next != null && setCursor(next)}>Next files</Button>
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}
