import { Alert, Button, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { getIntakeReadiness, listProcessingRuns, queueSearchIndex } from "../../../api/queue";
import { getScopeOverview } from "../../../api/scopes";
import { queuePollInterval } from "../../../domain/workflow";
import { useProcessingFlows } from "../../queue/components/ProcessingFlowSelect";

const library = { scope_type: "root" as const };
const activityPath = "/intake?tab=activity";
const unfinished = ["pending", "queued", "running", "pausing", "paused", "cancelling"];

export function SearchIndexPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const overview = useQuery({ queryKey: ["scopes", "overview", library], queryFn: () => getScopeOverview(library) });
  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness });
  const flows = useProcessingFlows();
  const runs = useQuery({ queryKey: ["processing-runs"], queryFn: listProcessingRuns,
    refetchInterval: query => queuePollInterval(query.state.data?.runs) });
  const queue = useMutation({
    mutationFn: queueSearchIndex,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["processing-runs"] });
      navigate(activityPath);
    },
  });

  const embedder = readiness.data?.embedders.find(item => item.id === readiness.data?.defaults.embedder);
  const semanticEmbedderReady = Boolean(embedder?.available && !embedder.lexical && embedder.id !== "local.hashing");
  const defaults = flows.data?.flows.find(flow => flow.id === "bundled");
  const processing = overview.data?.processing;
  const textCount = processing?.text_count ?? 0;
  const unread = (overview.data?.file_count ?? 0) - textCount;
  const indexExists = processing?.semantic_index.status === "ready";
  const busy = runs.data?.runs.some(run =>
    (run.operations?.embed || run.tool_label === "Full index rebuild") && unfinished.includes(run.status),
  );
  const readinessError = overview.error ?? readiness.error ?? flows.error ?? runs.error;
  const error = queue.error ?? readinessError;
  const loading = overview.isPending || readiness.isPending || flows.isPending || runs.isPending;
  const canBuild = !loading && !readinessError && Boolean(defaults && semanticEmbedderReady && textCount && !unread && !busy);

  return (
    <Stack spacing={2} sx={{ maxWidth: 880 }}>
      <Typography component="h1" variant="h5" fontWeight={750}>Search index</Typography>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography variant="body2">Build a semantic search index from your library’s saved text.</Typography>
          {loading && <LinearProgress aria-label="Checking index readiness" />}
          {processing && <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            <Typography variant="body2">Saved text <strong>{textCount.toLocaleString()}/{overview.data?.file_count.toLocaleString()}</strong></Typography>
            <Typography variant="body2">Indexed <strong>{processing.indexed_count.toLocaleString()}/{textCount.toLocaleString()}</strong></Typography>
            {semanticEmbedderReady && <Typography variant="body2">Embedding model <strong>{embedder?.model || embedder?.display_name}</strong></Typography>}
          </Stack>}
          {readiness.isSuccess && !semanticEmbedderReady && (
            <Alert severity="warning" action={<Button component={Link} to="/admin/processors?step=embedding">Model setup</Button>}>
              Connect a working semantic embedding model.
            </Alert>
          )}
          {overview.isSuccess && (!textCount || unread > 0) && (
            <Alert severity="info" action={<Button component={Link} to="/intake?step=text">Read documents</Button>}>
              {unread > 0 ? `${unread.toLocaleString()} library ${unread === 1 ? "file needs" : "files need"} readable text before indexing.`
                : "Add and read documents to build your first index."}
            </Alert>
          )}
          {busy && <Alert severity="info">An embedding run is already in the queue.</Alert>}
          {error && <Alert severity="error">{error.message}</Alert>}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button variant="contained" disabled={!canBuild || queue.isPending}
              onClick={() => defaults && queue.mutate({ chunk_size: defaults.chunk_size, chunk_overlap: defaults.chunk_overlap })}>
              {queue.isPending ? "Queueing…" : indexExists ? "Rebuild index" : "Build index"}
            </Button>
            <Button component={Link} to={activityPath}>View queue</Button>
          </Stack>
        </Stack>
      </Paper>
    </Stack>
  );
}
