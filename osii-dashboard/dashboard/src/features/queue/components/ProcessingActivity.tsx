import { useEffect, useRef } from "react";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import PauseCircleOutlineOutlinedIcon from "@mui/icons-material/PauseCircleOutlineOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import type { ProcessingRun } from "../../../api/types";

export type ProcessingAction = "start" | "pause" | "resume" | "cancel" | "retry";
function secondsBetween(start?: string | null, end?: string | null): number | null {
  if (!start) return null;
  const startMs = Date.parse(start);
  const endMs = end ? Date.parse(end) : Date.now();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return null;
  return Math.max(0, (endMs - startMs) / 1000);
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "not recorded";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remainder}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function completedFileDurations(run: ProcessingRun): number[] {
  return (run.items ?? []).flatMap((item) => (
    typeof item.duration_seconds === "number" && Number.isFinite(item.duration_seconds)
      ? [item.duration_seconds]
      : []
  ));
}

export function ProcessingActivity({ recentRuns, workerAvailable, selectedLogRunId, setSelectedLogRunId, controllingRun, controlRun, displayedLogLines, refreshLogs, logError = false, onRestage }: {
  recentRuns: ProcessingRun[]; workerAvailable?: boolean; selectedLogRunId: string | null;
  setSelectedLogRunId: (id: string) => void; controllingRun: string | null;
  controlRun: (run: ProcessingRun, action: ProcessingAction) => void | Promise<void>;
  displayedLogLines: string[]; refreshLogs: () => unknown; logError?: boolean; onRestage?: (run: ProcessingRun) => void;
}) {
  const selectedLogRun = recentRuns.find(run => run.id === selectedLogRunId);
  const logPanelRef = useRef<HTMLPreElement | null>(null);
  useEffect(() => { if (logPanelRef.current) logPanelRef.current.scrollTop = logPanelRef.current.scrollHeight; }, [displayedLogLines.length, selectedLogRunId]);
  return (      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1} alignItems={{ sm: "center" }}>
            <Typography fontWeight={700}>Processing activity</Typography>
            <Chip
              size="small"
              color={workerAvailable === false ? "error" : workerAvailable ? "success" : "default"}
              label={workerAvailable === undefined ? "Activity refreshes automatically" : workerAvailable ? "Worker responding" : "Worker unavailable"}
            />
          </Stack>
          {recentRuns.some((run) => ["queued", "pending", "running", "pausing", "cancelling"].includes(run.status)) ? (
            <Alert severity="info">
              Runs use one worker and process files sequentially. Pause a long run to let a newly queued priority run go next; pausing or cancelling takes effect safely after the current file finishes.
            </Alert>
          ) : null}
          {recentRuns.map((run) => {
            const durations = completedFileDurations(run);
            const processorSeconds = durations.reduce((total, duration) => total + duration, 0);
            const averageSeconds = durations.length ? processorSeconds / durations.length : null;
            const remainingFiles = Math.max(0, (run.total ?? 0) - (run.completed ?? 0));
            const estimatedRemaining = averageSeconds == null ? null : averageSeconds * remainingFiles;
            const elapsedSeconds = secondsBetween(run.started_at, run.finished_at);
            const itemErrors = (run.items ?? []).filter((item) => item.error);
            const controllable = Boolean(run.workflow);
            const canPause = controllable && ["queued", "pending", "running"].includes(run.status);
            const canResume = controllable && run.status === "paused";
            const canCancel = controllable && ["staged", "queued", "pending", "running", "pausing", "paused"].includes(run.status);
            const canRetry = controllable && (run.status === "error" || run.indexing_status === "error");
            return (
              <Paper key={run.id} variant="outlined" sx={{ p: 1.5 }}>
              <Stack
                direction={{ xs: "column", sm: "row" }}
                justifyContent="space-between"
                spacing={1}
              >
                <Stack>
                  <Typography fontWeight={600}>
                    {run.workflow === "library" ? "Library processing" : "New file intake"} · {run.id.slice(0, 8)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {run.completed ?? 0} / {run.total ?? 0} files · {run.created_at}
                  </Typography>
                  {(run.embedding_target?.model || run.embedding_model) && <Typography variant="caption" color="text.secondary">Embedding model: {run.embedding_target?.model || run.embedding_model}</Typography>}
                  {run.expert_context ? (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{
                        mt: 0.5,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      Expert context: {run.expert_context}
                    </Typography>
                  ) : null}
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                    {run.operations?.extract ? <Chip size="small" label="Extraction" /> : null}
                    {run.operations?.synthesize ? <Chip size="small" label={`Synthesis: ${run.operations.synthesize}`} /> : null}
                    {run.operations?.embed ? <Chip size="small" label={`Embedding${run.indexing_status ? `: ${run.indexing_status}` : ""}`} /> : null}
                    {run.operations?.enrich ? <Chip size="small" label={`Enrichment: ${run.operations.enrich}`} /> : null}
                  </Stack>
                </Stack>
                <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Button
                    size="small"
                    variant={selectedLogRunId === run.id ? "contained" : "text"}
                    onClick={() => setSelectedLogRunId(run.id)}
                  >
                    View log
                  </Button>
                  {run.status === "staged" ? <Button color="secondary" variant="contained" disabled={controllingRun !== null} onClick={() => void controlRun(run, "start")}>Start processing</Button> : null}
                  {canPause ? (
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<PauseCircleOutlineOutlinedIcon />}
                      disabled={controllingRun !== null}
                      onClick={() => void controlRun(run, "pause")}
                    >
                      Pause
                    </Button>
                  ) : null}
                  {canResume ? (
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<PlayArrowOutlinedIcon />}
                      disabled={controllingRun !== null}
                      onClick={() => void controlRun(run, "resume")}
                    >
                      Resume
                    </Button>
                  ) : null}
                  {canCancel ? (
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      startIcon={<CancelOutlinedIcon />}
                      disabled={controllingRun !== null}
                      onClick={() => void controlRun(run, "cancel")}
                    >
                      Cancel
                    </Button>
                  ) : null}
                  {run.status === "error" && itemErrors.length > 0 && onRestage && <Button color="secondary" variant="outlined" onClick={() => onRestage(run)}>Restage failed files</Button>}
                  {canRetry ? (
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<RefreshOutlinedIcon />}
                      disabled={controllingRun !== null || workerAvailable === false}
                      onClick={() => void controlRun(run, "retry")}
                    >
                      {(run.error_phase === "embedding" || run.indexing_status === "error") ? "Retry embeddings" : "Retry failed run"}
                    </Button>
                  ) : null}
                  <Chip
                    color={
                      run.status === "done"
                        ? "success"
                        : ["error", "cancelled"].includes(run.status)
                          ? "error"
                          : run.status === "paused"
                            ? "warning"
                            : "primary"
                    }
                    label={run.status}
                  />
                </Stack>
              </Stack>
              <Stack spacing={0.5} sx={{ mt: 1.5 }}>
                <Typography variant="caption">File processing: {run.completed ?? 0} of {run.total ?? 0} finished{itemErrors.length ? ` · ${itemErrors.length} with errors` : ""}</Typography>
                <LinearProgress aria-label={`File progress for run ${run.id}`} variant="determinate" value={(run.total ?? 0) > 0 ? Math.min(100, (run.completed ?? 0) / (run.total ?? 1) * 100) : 0} color={itemErrors.length || run.status === "error" ? "error" : "secondary"} sx={{ height: 7, borderRadius: 1 }} />
                {run.operations?.embed ? <Typography variant="caption" color={run.indexing_status === "error" ? "error.main" : "text.secondary"}>Semantic index: {run.indexing_status === "done" ? "saved — library checkpoints will refresh" : run.indexing_status === "running" ? "building; finished files do not mean the index is ready yet" : run.indexing_status === "error" ? "incomplete — retry reuses saved chunks and completed documents" : "waiting or paused; saved chunks are retained"}</Typography> : null}
                {run.indexing_status === "running" ? <LinearProgress aria-label="Building semantic index" /> : null}
                {run.indexing_progress && <Typography variant="caption">Selected embeddings: {run.indexing_progress.completed_documents} of {run.indexing_progress.total_documents} documents complete · {run.indexing_progress.embedded_chunks} chunks saved this attempt · {run.indexing_progress.reused_chunks} reused from checkpoints or the index</Typography>}
                {run.indexing_progress && Object.keys(run.indexing_progress.failures).length > 0 && <Alert severity="warning">{Object.keys(run.indexing_progress.failures).length} document(s) still need embeddings. Successful work is retained.<details><summary>Embedding failures</summary>{Object.entries(run.indexing_progress.failures).map(([id, error]) => <Typography key={id} variant="caption" component="div" sx={{ overflowWrap: "anywhere" }}>{run.items?.find(item => item.file_id === id)?.display || id}: {error}</Typography>)}</details></Alert>}
              </Stack>
              {run.started_at ? (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  Elapsed {formatDuration(elapsedSeconds)}
                  {durations.length ? ` · measured processor time ${formatDuration(processorSeconds)} · average ${formatDuration(averageSeconds)} per completed file` : ""}
                  {estimatedRemaining != null && remainingFiles > 0 ? ` · estimated remaining ${formatDuration(estimatedRemaining)}` : ""}
                </Typography>
              ) : null}
              {run.status === "pausing" ? <Alert severity="info" sx={{ mt: 1 }}>Finishing the current file before pausing.</Alert> : null}
              {run.status === "cancelling" ? <Alert severity="info" sx={{ mt: 1 }}>Finishing the current file before cancelling.</Alert> : null}
              {run.error ? <Alert severity="error" sx={{ mt: 1 }}>{run.error}</Alert> : null}
              {run.indexing_error && run.indexing_error !== run.error ? <Alert severity="error" sx={{ mt: 1 }}>{run.indexing_error}</Alert> : null}
              {itemErrors.length ? (
                <Alert severity="error" sx={{ mt: 1 }}>
                  {itemErrors.slice(0, 3).map((item, index) => (
                    <Typography key={`${item.display}-${index}`} variant="body2">
                      {item.display}: {item.error}
                    </Typography>
                  ))}
                  {itemErrors.length > 3 ? `And ${itemErrors.length - 3} more file error(s).` : null}
                </Alert>
              ) : null}
              {(run.logs ?? []).slice(-2).map((line) => (
                <Typography
                  key={line}
                  variant="caption"
                  display="block"
                  color="text.secondary"
                >
                  {line}
                </Typography>
              ))}
              {(run.items ?? []).length > 0 ? (
                <Accordion variant="outlined" disableGutters sx={{ mt: 1 }}>
                  <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
                    <Typography variant="body2" fontWeight={600}>Files and progress</Typography>
                  </AccordionSummary>
                  <AccordionDetails sx={{ maxHeight: 300, overflow: "auto" }}>
                    <Stack spacing={1}>
                      {durations.length ? (
                        <Typography variant="caption" color="text.secondary">
                          Fastest {formatDuration(Math.min(...durations))} · slowest {formatDuration(Math.max(...durations))} · average {formatDuration(averageSeconds)}
                        </Typography>
                      ) : null}
                      {(run.items ?? []).map((item, index) => (
                        <Stack
                          key={`${item.display}-${index}`}
                          direction={{ xs: "column", sm: "row" }}
                          justifyContent="space-between"
                          spacing={0.5}
                        >
                          <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{item.display}</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                            {item.status}{item.current_step ? ` · ${item.current_step}` : ""} · {formatDuration(
                              item.duration_seconds ?? secondsBetween(item.started_at, item.finished_at),
                            )}
                          </Typography>
                        </Stack>
                      ))}
                    </Stack>
                  </AccordionDetails>
                </Accordion>
              ) : null}
              </Paper>
            );
          })}
          {selectedLogRunId ? (
            <Paper
              variant="outlined"
              sx={{
                bgcolor: "#10151d",
                color: "#d8e2ef",
                borderColor: "#344155",
                overflow: "hidden",
              }}
            >
              <Stack
                direction={{ xs: "column", sm: "row" }}
                justifyContent="space-between"
                alignItems={{ sm: "center" }}
                spacing={1}
                sx={{ px: 1.5, py: 1, borderBottom: "1px solid #344155" }}
              >
                <Typography variant="body2" fontWeight={700} color="inherit">
                  Live run log · {selectedLogRunId.slice(0, 8)}
                  {selectedLogRun ? ` · ${selectedLogRun.status}` : ""}
                </Typography>
                <Stack direction="row" spacing={1}>
                  <Button size="small" color="inherit" onClick={() => void refreshLogs()}>
                    Refresh
                  </Button>
                </Stack>
              </Stack>
              <Box
                component="pre"
                ref={logPanelRef}
                aria-live="polite"
                sx={{
                  m: 0,
                  p: 1.5,
                  minHeight: 120,
                  maxHeight: 300,
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                  fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                  fontSize: "0.78rem",
                  lineHeight: 1.55,
                }}
              >
                {logError
                  ? "Could not load this run log. Use Refresh after confirming the backend is available."
                  : displayedLogLines.join("\n")
                    || "No log entries yet. Start a staged plan to begin processing."}
              </Box>
            </Paper>
          ) : null}
          {!recentRuns.length ? (
            <Typography color="text.secondary">No intake runs yet.</Typography>
          ) : null}
        </Stack>
      </Paper>);
}
