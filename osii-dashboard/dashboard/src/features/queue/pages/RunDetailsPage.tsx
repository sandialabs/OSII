import { useState } from "react";
import {
  Alert, Box, Button, Chip, LinearProgress, Paper, Stack, TextField, Typography,
} from "@mui/material";
import ContentCopyOutlined from "@mui/icons-material/ContentCopyOutlined";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { ApiError } from "../../../api/client";
import { controlProcessingRun, getProcessingRun, getProcessingRunLogs } from "../../../api/queue";
import type { ProcessingRun } from "../../../api/types";
import { PageBreadcrumbs } from "../../../components/workbench/PageBreadcrumbs";
import { failedRunFiles, processingStatus, recordedFileStages, runHasFailures, runReport, runStatusLabel, runTitle } from "../../../domain/processingRun";
import { flowTestError } from "../../../domain/processingFlowTests";
import { isActiveRun } from "../../../domain/workflow";
import { QUEUE_ACTIVITY_PATH } from "../../../utils/routes";
import { RunFiles } from "../components/RunFiles";

const parents = [{ label: "Queue & activity", to: QUEUE_ACTIVITY_PATH }];
const diagnosticText = (error: string) => flowTestError({ ok: false, detail: error }, "Copy run report");

function RunIssues({ run }: { run: ProcessingRun }) {
  const failed = failedRunFiles(run);
  const indexErrors = Object.entries(run.indexing_progress?.failures ?? {});
  const messages = [...new Set([run.error, run.indexing_error].filter((message): message is string => Boolean(message)))];
  // Some older runs saved the worker's terminal error only as the last log entry.
  if (!messages.length && run.status === "error") {
    messages.push(run.logs?.slice(-1)[0] ?? "The run failed. Open the run log for details.");
  }
  const files = failed.map(item => {
    const problems = [
      { processor: item.extractor, error: item.extract_error },
      { processor: item.synthesizer, error: item.synthesis_error },
      { processor: item.enricher, error: item.enrichment_error },
    ].filter(problem => problem.error);
    const last = item.diagnostics?.slice(-1)[0];
    const processor = typeof last?.processor === "string" ? last.processor : undefined;
    return {
      label: item.display, path: item.source_relpath ?? item.path,
      problems: problems.length ? problems : [{ processor, error: item.error ?? "No error message was recorded." }],
    };
  });
  const recorded = new Map((run.items ?? []).filter(item => item.file_id).map(item => [item.file_id, item]));
  const embeddings = indexErrors.flatMap(([id, error]) => {
    const item = recorded.get(id);
    if (item?.error === error) return [];
    return [{ label: item?.display ?? id, path: item?.source_relpath ?? item?.path, problems: [{ processor: run.embedding_target?.provider, error }] }];
  });
  const entries = [...files, ...embeddings];
  const [limit, setLimit] = useState(10);
  return (
    <Paper component="section" variant="outlined" aria-labelledby="run-failures" sx={{ p: 2, borderColor: "error.main" }}>
      <Stack spacing={1.25}>
        <Typography id="run-failures" component="h2" variant="h6">Failures</Typography>
        {messages.map(message => <Alert key={message} severity="error" sx={{ overflowWrap: "anywhere" }}>{diagnosticText(message)}</Alert>)}
        {entries.slice(0, limit).map(({ label, path, problems }, index) => (
          <Box key={index} sx={{ overflowWrap: "anywhere" }}>
            <Typography variant="body2" fontWeight={700}>{label}</Typography>
            {path && path !== label && <Typography variant="caption" color="text.secondary">{path}</Typography>}
            {problems.map(({ processor, error }, i) => (
              <Typography key={i} variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                {processor && <strong>{processor} · </strong>}{diagnosticText(error ?? "")}
              </Typography>
            ))}
          </Box>
        ))}
        {entries.length > limit && <Button sx={{ alignSelf: "start" }} onClick={() => setLimit(limit + 10)}>Show more failures</Button>}
      </Stack>
    </Paper>
  );
}

function RunDetails({ run, refresh }: { run: ProcessingRun; refresh: () => Promise<unknown> }) {
  const client = useQueryClient();
  const [logOpen, setLogOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState("");
  const [report, setReport] = useState<string | null>(null);
  const active = isActiveRun(run.status);
  const hasFailures = runHasFailures(run);
  const logs = useQuery({
    queryKey: ["processing-runs", "detail", run.id, "logs"],
    queryFn: ({ signal }) => getProcessingRunLogs(run.id, signal),
    enabled: logOpen,
    refetchInterval: active ? 3000 : false,
  });
  const control = useMutation({
    mutationFn: (action: Parameters<typeof controlProcessingRun>[1]) => controlProcessingRun(run.id, action),
    onSuccess: async () => {
      await Promise.all([refresh(), client.invalidateQueries({ queryKey: ["processing-runs"] })]);
    },
  });
  const formattedReport = () => JSON.stringify(runReport(run, run.logs ?? logs.data?.logs), null, 2);
  const copy = async () => {
    const text = formattedReport();
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus("Run report copied.");
    } catch {
      setReport(text);
      setCopyStatus("Clipboard unavailable. Select and copy the report below.");
    }
  };

  const actions: { action: Parameters<typeof controlProcessingRun>[1]; label: string }[] = [];
  if (run.workflow && ["pending", "queued", "running"].includes(run.status)) actions.push({ action: "pause", label: "Pause" });
  if (run.workflow && run.status === "paused") actions.push({ action: "resume", label: "Resume" });
  if (run.workflow && ["staged", "pending", "queued", "running", "pausing", "paused"].includes(run.status)) actions.push({ action: "cancel", label: "Cancel" });
  if (run.workflow && (run.status === "error" || run.status === "done" && hasFailures)) {
    const label = run.error_phase === "embedding" || run.indexing_status === "error" ? "Retry embeddings"
      : failedRunFiles(run).length && run.workflow !== "tool" ? "Retry failed files" : "Retry run";
    actions.push({ action: "retry", label });
  }
  const models = Object.entries(run.model_targets ?? {});
  const indexed = new Set(run.indexing_file_ids);
  const processors = [...new Set([
    run.tool_id, run.embedding_target?.provider,
    ...(run.items ?? []).flatMap(item => recordedFileStages(run, item, indexed)
      .filter(stage => !["skipped", "reused", "queued"].includes(stage.status)).map(stage => stage.processor)),
  ].filter(Boolean))];
  const lines = logs.data?.logs ?? run.logs ?? [];
  return (
    <>
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" spacing={1} useFlexGap>
        <Stack spacing={0.5} minWidth={0}>
          <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
            <Typography component="h1" variant="h5" fontWeight={750} sx={{ overflowWrap: "anywhere" }}>{runTitle(run)}</Typography>
            <Chip label={runStatusLabel(run)} size="small" color={hasFailures ? "warning" : run.status === "done" ? "success" : "default"} />
          </Stack>
          <Typography variant="body2" color="text.secondary">{new Date(run.created_at).toLocaleString()} · Run {run.id}</Typography>
        </Stack>
        <Stack spacing={0.5}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button variant="contained" startIcon={<ContentCopyOutlined />} onClick={() => void copy()}>Copy run report</Button>
            <Button aria-expanded={report !== null} onClick={() => setReport(report === null ? formattedReport() : null)}>
              {report === null ? "View diagnostics" : "Hide diagnostics"}
            </Button>
          </Stack>
          {copyStatus && <Typography role="status" variant="body2">{copyStatus}</Typography>}
        </Stack>
      </Stack>
      {hasFailures && <RunIssues run={run} />}
      {report && <TextField label="Run report" multiline rows={8} value={report} inputProps={{ readOnly: true, style: { fontFamily: "monospace" } }} />}
      {control.isError && <Alert severity="error">{control.error.message}</Alert>}
      {(actions.length > 0 || active) && (
        <Stack spacing={1}>
          {active && <LinearProgress aria-label="Run progress" variant={run.total ? "determinate" : "indeterminate"}
            value={Math.min(100, (run.completed ?? 0) / Math.max(1, run.total ?? 0) * 100)} />}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {actions.map(({ action, label }) => (
              <Button key={action} variant="outlined" color={action === "cancel" ? "error" : "primary"}
                disabled={control.isPending} onClick={() => control.mutate(action)}>{label}</Button>
            ))}
          </Stack>
        </Stack>
      )}
      {(processors.length > 0 || models.length > 0 || run.indexing_status) && (
        <Paper component="section" variant="outlined" aria-labelledby="run-processors" sx={{ p: 2 }}>
          <Stack spacing={0.75}>
            <Typography id="run-processors" component="h2" variant="h6">Processors and models</Typography>
            {processors.length > 0 && <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{processors.join(" · ")}</Typography>}
            {models.map(([kind, target]) => <Typography key={kind} variant="body2" sx={{ overflowWrap: "anywhere" }}>
              {kind === "embedder" ? "Embedding" : kind === "synthesizer" ? "Synthesis" : kind} · {target.model || target.alias}{target.endpoint ? ` · ${target.endpoint}` : ""}
            </Typography>)}
            {run.indexing_status && <Typography variant="body2">
              Embeddings · {processingStatus(run.indexing_status)}
              {run.indexing_progress ? ` · ${run.indexing_progress.completed_documents}/${run.indexing_progress.total_documents} documents` : ""}
            </Typography>}
          </Stack>
        </Paper>
      )}
      <RunFiles run={run} />
      <Paper component="details" variant="outlined" onToggle={event => setLogOpen(event.currentTarget.open)} sx={{ p: 2 }}>
        <Box component="summary" sx={{ cursor: "pointer", fontWeight: 700 }}>Run log</Box>
        {logOpen && <Stack spacing={1} sx={{ mt: 1 }}>
          <Button size="small" onClick={() => void logs.refetch()} sx={{ alignSelf: "start" }}>Refresh log</Button>
          {logs.isError && <Alert severity="warning">Could not refresh the log.</Alert>}
          <Box component="pre" sx={{ maxHeight: 400, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12, m: 0 }}>
            {lines.join("\n") || (logs.isPending ? "Loading log…" : "No log entries yet.")}
          </Box>
        </Stack>}
      </Paper>
    </>
  );
}

export function RunDetailsPage() {
  const { runId = "" } = useParams();
  const run = useQuery({
    queryKey: ["processing-runs", "detail", runId],
    queryFn: ({ signal }) => getProcessingRun(runId, signal),
    refetchInterval: query => isActiveRun(query.state.data?.status) ? 3000 : false,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
  return (
    <Stack spacing={2} sx={{ maxWidth: 1120, mx: "auto" }}>
      <PageBreadcrumbs parents={parents} current={`Run ${runId.slice(0, 8)}`} />
      {run.isPending && <LinearProgress aria-label="Loading run" />}
      {run.isError && <Alert severity="error" action={<Button onClick={() => void run.refetch()}>Retry</Button>}>{run.error.message}</Alert>}
      {run.data && <RunDetails key={runId} run={run.data} refresh={run.refetch} />}
    </Stack>
  );
}
