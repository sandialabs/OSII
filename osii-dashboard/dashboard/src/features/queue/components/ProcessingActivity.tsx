import { useEffect, useRef, useState } from "react";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import type { ProcessingRun } from "../../../api/types";

export type ProcessingAction = "start" | "pause" | "resume" | "cancel" | "retry";
const active = (status: string) => ["pending", "queued", "running", "pausing", "cancelling"].includes(status);
function diagnosticReport(run: ProcessingRun) {
  return {run_id: run.id, queue_job_id: run.queue_job_id, workflow: run.workflow,
    processing_flow: run.processing_flow, status: run.status, created_at: run.created_at, selection: run.selection,
    operations: run.operations, models: run.model_targets, embedding: run.embedding_target,
    indexing_status: run.indexing_status, indexing_progress: run.indexing_progress,
    error: run.error, indexing_error: run.indexing_error, diagnostics: run.diagnostics, logs: run.logs, items: run.items};
}

export function ProcessingActivity({ recentRuns, workerAvailable, selectedLogRunId, setSelectedLogRunId, controllingRun, controlRun, displayedLogLines, refreshLogs, logError = false, onRestage }: {
  recentRuns: ProcessingRun[]; workerAvailable?: boolean; selectedLogRunId: string | null;
  setSelectedLogRunId: (id: string | null) => void; controllingRun: string | null;
  controlRun: (run: ProcessingRun, action: ProcessingAction) => void | Promise<void>;
  displayedLogLines: string[]; refreshLogs: () => unknown; logError?: boolean;
  onRestage?: (run: ProcessingRun) => void;
}) {
  const [showOlder, setShowOlder] = useState(false);
  const visibleRuns = showOlder ? recentRuns : [...recentRuns.filter(run => active(run.status)), ...recentRuns.filter(run => !active(run.status)).slice(0, 5)];
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const [diagnostics, setDiagnostics] = useState<Set<string>>(new Set());
  const [copyMessage, setCopyMessage] = useState<{id: string; text: string} | null>(null);
  const logRef = useRef<HTMLPreElement | null>(null);
  useEffect(() => {if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;}, [displayedLogLines.length, selectedLogRunId]);
  const copy = async (run: ProcessingRun) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(diagnosticReport(run), null, 2));
      setCopyMessage({id: run.id, text: "Diagnostics copied"});
    } catch {
      setDiagnostics(previous => new Set(previous).add(run.id));
      setCopyMessage({id: run.id, text: "Clipboard unavailable. Select and copy the report below."});
    }
  };
  return <Paper variant="outlined" sx={{p: 2}}><Stack spacing={1.5}>
    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
      <Typography variant="h6">Processing</Typography>
      <Chip size="small" color={workerAvailable === false ? "error" : workerAvailable ? "success" : "default"} label={workerAvailable === false ? "Worker unavailable" : workerAvailable ? "Worker connected" : "Checking worker"} />
    </Stack>
    {!recentRuns.length && <Typography color="text.secondary">No processing runs yet.</Typography>}
    {visibleRuns.map(run => {
      const errors = (run.items ?? []).filter(item => item.error);
      const failed = run.status === "error" || run.indexing_status === "error" || errors.length > 0;
      const expanded = active(run.status) || opened.has(run.id);
      const canPause = Boolean(run.workflow) && ["queued", "pending", "running"].includes(run.status);
      const canCancel = Boolean(run.workflow) && ["staged", "queued", "pending", "running", "pausing", "paused"].includes(run.status);
      const canRetry = Boolean(run.workflow) && failed && !active(run.status) && run.status !== "cancelled";
      const runningFile = run.items?.find(item => item.status === "running");
      const runningProcessor = runningFile?.current_step === "Generate summary" ? run.operations?.synthesize
        : runningFile?.current_step === "Run enrichment" ? run.operations?.enrich
        : runningFile?.current_step === "Check source" ? null : runningFile?.extractor;
      const selectedModels = [...new Set(Object.values(run.model_targets ?? {}).map(item => item.model || item.alias))];
      return <Accordion key={run.id} variant="outlined" disableGutters expanded={expanded} onChange={(_, show) => {
        setOpened(previous => {const next = new Set(previous); if (show) next.add(run.id); else next.delete(run.id); return next;});
        if (!show && selectedLogRunId === run.id) setSelectedLogRunId(null);
      }}>
        <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}><Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography fontWeight={600}>{run.processing_flow?.name || run.tool_label || (run.workflow === "tool" ? "Tool run" : "File processing")}</Typography>
          <Chip size="small" color={failed ? "warning" : run.status === "done" ? "success" : "default"} label={run.status === "done" && failed ? "Completed with issues" : run.status === "error" ? "Failed" : run.status} />
          <Typography variant="body2">{run.completed ?? 0}/{run.total ?? 0} finished{errors.length ? ` · ${errors.length} failed` : ""}</Typography>
          <Typography variant="caption" color="text.secondary">{new Date(run.created_at).toLocaleString()}</Typography>
        </Stack></AccordionSummary>
        {expanded && <AccordionDetails><Stack spacing={1.5}>
          <Typography variant="caption">Run {run.id} · Job {run.queue_job_id || "—"}</Typography>
          {run.processing_flow && <Typography variant="body2"><strong>Flow:</strong> {run.processing_flow.name} · Extract → synthesize → enrich → embed</Typography>}
          <Box component="details"><Box component="summary" sx={{cursor: "pointer", fontWeight: 600}}>Files & processes ({run.items?.length ?? run.selection?.paths.length ?? 0})</Box><Stack spacing={1} sx={{pt: 1}}>{run.items?.map((item, i) => <Box key={i}><Typography variant="body2" fontWeight={600}>{item.display} · {item.status}</Typography><Typography variant="caption">Reader: {item.extractor || "—"} · Synthesis: {item.synthesizer || run.operations?.synthesize || "—"} · Enrichment: {item.enricher || run.operations?.enrich || "—"}</Typography></Box>)}</Stack></Box>
          {selectedModels.length > 0 && <Typography variant="body2" color="text.secondary">{selectedModels.join(" · ")}</Typography>}
          {runningFile && <Typography variant="body2">{runningFile.current_step || "Processing"}: {runningFile.display}{runningProcessor ? ` · ${runningProcessor}` : ""}</Typography>}
          {active(run.status) && <LinearProgress aria-label={`File progress for run ${run.id}`} variant={(run.total ?? 0) > 0 ? "determinate" : "indeterminate"} value={Math.min(100, (run.completed ?? 0) / Math.max(1, run.total ?? 0) * 100)} />}
          {run.indexing_status && run.operations?.embed && <Stack spacing={0.5}><Typography variant="body2">Embeddings: {run.indexing_status}{run.indexing_progress ? ` · ${run.indexing_progress.completed_documents}/${run.indexing_progress.total_documents} documents` : ""}</Typography>{run.indexing_status === "running" && <LinearProgress aria-label="Building embeddings" />}</Stack>}
          {run.status === "pausing" && <Alert severity="info">Pausing after the current file or provider request.</Alert>}
          {run.status === "cancelling" && <Alert severity="info">Cancelling after the current file or provider request.</Alert>}
          {run.error && <Alert severity="error" sx={{overflowWrap: "anywhere"}}>{run.error}</Alert>}
          {run.indexing_error && run.indexing_error !== run.error && <Alert severity="error">{run.indexing_error}</Alert>}
          {errors.length > 0 && <details><summary>{errors.length} file {errors.length === 1 ? "issue" : "issues"}</summary>{errors.map((item, i) => {
            const incident = item.diagnostics?.[item.diagnostics.length - 1];
            const processor = typeof incident?.processor === "string" ? incident.processor : item.current_step === "Check source" ? "Core file reader" : item.extractor || "Processing";
            return <Box key={i} sx={{py: 1}}><Typography fontWeight={600} variant="body2">{item.display} · {processor}</Typography><Typography variant="body2" sx={{whiteSpace: "pre-wrap", overflowWrap: "anywhere"}}>{item.error}</Typography></Box>;
          })}</details>}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {canPause && <Button disabled={Boolean(controllingRun)} onClick={() => void controlRun(run, "pause")}>Pause</Button>}
            {run.status === "paused" && run.workflow && <Button disabled={Boolean(controllingRun)} onClick={() => void controlRun(run, "resume")}>Resume</Button>}
            {canCancel && <Button color="error" disabled={Boolean(controllingRun)} onClick={() => void controlRun(run, "cancel")}>Cancel</Button>}
            {canRetry && <Button variant="contained" disabled={Boolean(controllingRun)} onClick={() => void controlRun(run, "retry")}>{run.error_phase === "embedding" || run.indexing_status === "error" ? "Retry embeddings" : "Retry failed files"}</Button>}
            {onRestage && <Button onClick={() => onRestage(run)}>Use selection again</Button>}
            <Button onClick={() => void copy(run)}>Copy run report</Button>
            <Button onClick={() => setDiagnostics(previous => {const next = new Set(previous); if (next.has(run.id)) next.delete(run.id); else next.add(run.id); return next;})}>{diagnostics.has(run.id) ? "Hide selections & diagnostics" : "Selections & diagnostics"}</Button>
            <Button onClick={() => setSelectedLogRunId(selectedLogRunId === run.id ? null : run.id)}>{selectedLogRunId === run.id ? "Hide log" : "View log"}</Button>
          </Stack>
          {copyMessage?.id === run.id && <Typography variant="caption" role="status">{copyMessage.text}</Typography>}
          {diagnostics.has(run.id) && <Box component="pre" sx={{maxHeight: 400, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12}}>{JSON.stringify(diagnosticReport(run), null, 2)}</Box>}
          {selectedLogRunId === run.id && <><Stack direction="row" justifyContent="space-between"><Typography variant="body2">Run log · {run.id.slice(0, 8)}</Typography><Button size="small" onClick={() => void refreshLogs()}>Refresh log</Button></Stack>{logError && <Alert severity="warning">Could not refresh the log.</Alert>}<Box component="pre" ref={logRef} sx={{maxHeight: 350, overflow: "auto", p: 1.5, bgcolor: "action.hover", fontSize: 12, whiteSpace: "pre-wrap"}}>{displayedLogLines.join("\n") || "No log entries yet."}</Box></>}
        </Stack></AccordionDetails>}
      </Accordion>;
    })}
    {recentRuns.length > visibleRuns.length && <Button onClick={() => setShowOlder(true)}>Show older runs ({recentRuns.length - visibleRuns.length})</Button>}
    {showOlder && recentRuns.filter(run => !active(run.status)).length > 5 && <Button onClick={() => setShowOlder(false)}>Hide older runs</Button>}
  </Stack></Paper>;
}
