import {useState} from "react";
import {Alert, Button, Chip, MenuItem, Paper, Stack, TextField, Typography} from "@mui/material";
import {useQuery, useQueryClient} from "@tanstack/react-query";
import {Link} from "react-router-dom";
import {getScopeOverview} from "../../../api/scopes";
import {apiJson} from "../../../api/client";
import {listProcessingRuns} from "../../../api/queue";
import {queuePollInterval} from "../../../domain/workflow";
import {ProcessingFlowSelect} from "../../queue/components/ProcessingFlowSelect";
export function CollectionProcessingStatus({collectionId}: {collectionId: string}) {
  const client = useQueryClient(); const [flow, setFlow] = useState("bundled"); const [mode, setMode] = useState("missing"); const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const runs = useQuery({queryKey: ["processing-runs"], queryFn: listProcessingRuns, refetchInterval: query => queuePollInterval(query.state.data?.runs)});
  const overview = useQuery({queryKey: ["collection-processing", collectionId, runs.data?.runs.map(run => `${run.id}:${run.status}:${run.completed}`).join(",")], queryFn: () => getScopeOverview({scope_type: "collection", collection_id: collectionId})});
  const processing = overview.data?.processing;
  const queue = async () => {setBusy(true); setMessage(""); try {await apiJson(`/api/collections/${encodeURIComponent(collectionId)}/process`, {method: "POST", json: {processing_flow_id: flow, mode}}); setMessage("Queued. View progress and diagnostics in Intake & Queue."); await client.invalidateQueries({queryKey: ["processing-runs"]});} catch (error) {setMessage((error as Error).message);} finally {setBusy(false);}};
  return <Paper variant="outlined" sx={{p: 2}}><Stack spacing={1.5}>
    <Typography variant="h6" fontWeight={700}>Processing status</Typography>
    {processing && <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{[["Read", processing.text_count], ["Summarized", processing.synthesis_count], ["Enriched", processing.enrichment_count], ["Embedded", processing.indexed_count]].map(([label, count]) => <Chip key={label} label={`${label}: ${count}/${overview.data?.file_count}`} />)}</Stack>}
    {overview.isError && <Alert severity="error">{overview.error.message}</Alert>}
    <ProcessingFlowSelect value={flow} onChange={setFlow} />
    <TextField select size="small" label="Collection processing" value={mode} onChange={event => setMode(event.target.value)}><MenuItem value="missing">Keep existing text · process collection</MenuItem><MenuItem value="reprocess">Reread originals · preserve extraction history</MenuItem></TextField>
    <Stack direction="row" spacing={1}><Button variant="contained" disabled={busy || !overview.data?.file_count} onClick={() => void queue()}>{busy ? "Queueing…" : "Process collection"}</Button><Button component={Link} to="/intake?tab=activity">View queue</Button></Stack>
    {message && <Alert severity="info">{message}</Alert>}
    {(runs.data?.runs ?? []).filter(run => run.collection_id === collectionId).slice(0, 5).map(run => <Typography variant="caption" key={run.id}>{run.processing_flow?.name || "Processing"} · {run.status} · {run.completed}/{run.total} files</Typography>)}
  </Stack></Paper>;
}
