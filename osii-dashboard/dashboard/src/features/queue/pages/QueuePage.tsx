import {useEffect, useState} from "react";
import {Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Paper, Stack, Tooltip, Typography} from "@mui/material";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import {useQuery, useQueryClient} from "@tanstack/react-query";
import {Link, useSearchParams} from "react-router-dom";
import {isActiveRun, queuePollInterval} from "../../../domain/workflow";
import {createProcessingRun, listProcessingRuns, resolveIntake} from "../../../api/queue";
import type {PickedFile} from "../../../components/discovery/LocationBrowser";
import {FileSelectionPanel} from "../components/FileSelectionPanel";
import {ProcessingFlowSelect} from "../components/ProcessingFlowSelect";
import {IntakeSections} from "../components/IntakeSections";
import {ProcessingActivity} from "../components/ProcessingActivity";
const selectionKey = "osii:intake-files";
function restoreFiles(): PickedFile[] {
  try {const value = JSON.parse(localStorage.getItem(selectionKey) || "[]"); return Array.isArray(value) ? value.filter(file => typeof file.path === "string" && typeof file.name === "string").slice(0, 10000) : [];} catch {return [];}
}
export function QueuePage() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const section = params.get("tab") === "activity" ? "activity" : "add";
  const [files, setFiles] = useState<PickedFile[]>(restoreFiles);
  const [flow, setFlow] = useState(() => sessionStorage.getItem("osii:intake-flow") || "bundled");
  useEffect(() => {try {sessionStorage.setItem("osii:intake-flow", flow);} catch { /* The selection remains usable in memory. */ }}, [flow]);
  const [help, setHelp] = useState(false);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<{severity: "error" | "success"; text: string} | null>(null);
  useEffect(() => {try {localStorage.setItem(selectionKey, JSON.stringify(files));} catch {setNotice({severity: "error", text: "Browser storage is full. Keep this Intake tab open to retain the selection."});}}, [files]);
  const runs = useQuery({queryKey: ["processing-runs"], queryFn: listProcessingRuns, refetchInterval: query => queuePollInterval(query.state.data?.runs)});
  const paths = files.map(file => file.path);
  const preview = useQuery({queryKey: ["intake", "selected-files", paths], queryFn: ({signal}) => resolveIntake({queue_paths: paths, include_subfolders: false, run_extraction: true, metadata_only: true}, signal), enabled: Boolean(files.length) && section === "add", retry: false, staleTime: Infinity, refetchOnWindowFocus: false});
  const count = preview.data?.preview.matched_count ?? 0;
  const queue = async () => {
    setStarting(true); setNotice(null);
    try {
      const run = await createProcessingRun({queue_paths: paths, include_subfolders: false, workflow: "intake", processing_flow_id: flow, extract_mode: "missing"});
      setParams({tab: "activity"}); setNotice({severity: "success", text: `Queued ${run.resolved_count ?? count} files.`});
      await client.invalidateQueries({queryKey: ["processing-runs"]});
    } catch (error) {setNotice({severity: "error", text: (error as Error).message});} finally {setStarting(false);}
  };
  return <Stack spacing={2} sx={{maxWidth: 1100, mx: "auto"}}>
    <Stack direction="row" alignItems="center"><Typography variant="h5" fontWeight={700}>Intake & Queue</Typography><IconButton aria-label="About Intake and Queue" onClick={() => setHelp(true)}><HelpOutlineIcon /></IconButton></Stack>
    <IntakeSections value={section} onChange={tab => setParams(tab === "activity" ? {tab: "activity"} : {})} activeCount={runs.data?.runs.filter(run => isActiveRun(run.status)).length ?? 0} />
    {notice && <Alert severity={notice.severity}>{notice.text}</Alert>}
    {section === "add" ? <><FileSelectionPanel files={files} onFiles={setFiles} /><Paper variant="outlined" sx={{p: 2}}><Stack spacing={1.5}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6" fontWeight={700}>2. Process</Typography>
        <Tooltip title="Configure and test flows in Setup">
          <IconButton component={Link} to="/admin/processors#processing-flows" aria-label="Configure and test flows in Setup"><SettingsOutlinedIcon /></IconButton>
        </Tooltip>
      </Stack>
      <ProcessingFlowSelect value={flow} onChange={setFlow} />
      {preview.isFetching && <Typography role="status" variant="body2">Checking access to selected files…</Typography>}
      {preview.isError && <Alert severity="error" action={<Button onClick={() => void preview.refetch()}>Retry file check</Button>}>{preview.error.message}</Alert>}
      {runs.data?.worker?.available === false && <Alert severity="warning">Worker unavailable. Queued files will wait.</Alert>}
      <Button variant="contained" disabled={!count || preview.isFetching || starting} onClick={() => void queue()}>{starting ? "Queueing…" : `Queue ${count} ${count === 1 ? "file" : "files"}`}</Button>
    </Stack></Paper></> : <><ProcessingActivity recentRuns={runs.data?.runs ?? []} workerAvailable={runs.data?.worker?.available} />{runs.isError && <Alert severity="error">{runs.error.message}</Alert>}</>}
    <Dialog open={help} onClose={() => setHelp(false)} fullWidth maxWidth="sm"><DialogTitle>Intake & Queue</DialogTitle><DialogContent><Stack spacing={1.5}><Typography><strong>Select files, choose a named flow, then queue.</strong> The default flow reads files, creates summaries and metadata, and updates the search index. Open a run from the queue to see failures or retry.</Typography><Typography><strong>Configure once in Setup.</strong> Each flow defines reader and fallback order and has a sample test. Your file selection is saved in this browser when visiting Setup.</Typography><Typography><strong>Collection reprocessing</strong> belongs in the collection’s Processing status section. Each run has a report with files, processors, errors, and logs. Read generated content from Files or Collections.</Typography></Stack></DialogContent><DialogActions><Button onClick={() => setHelp(false)}>Close</Button></DialogActions></Dialog>
  </Stack>;
}
