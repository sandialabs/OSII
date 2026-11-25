import { useEffect, useState } from "react";
import { Alert, Button, IconButton, Menu, MenuItem, Paper, Stack, Tooltip, Typography } from "@mui/material";
import ExpandMore from "@mui/icons-material/ExpandMore";
import HelpOutline from "@mui/icons-material/HelpOutline";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { isActiveRun, queuePollInterval } from "../../../domain/workflow";
import { createProcessingRun, listProcessingRuns, resolveIntake } from "../../../api/queue";
import { buildRunRoute, QUEUE_ACTIVITY_PATH } from "../../../utils/routes";
import type { PickedFile } from "../../../components/discovery/LocationBrowser";
import { PageBreadcrumbs } from "../../../components/workbench/PageBreadcrumbs";
import { FileSelectionPanel } from "../components/FileSelectionPanel";
import { ProcessingFlowSelect, useProcessingFlows } from "../components/ProcessingFlowSelect";
import { IntakeSections } from "../components/IntakeSections";
import { ProcessingActivity } from "../components/ProcessingActivity";
import { getQuickStart, QuickStartModels, type QuickStart } from "../components/QuickStartModels";

const selectionKey = "osii:intake-files";
const quickStartKey = ["quick-intake"];

function restoreFiles(): PickedFile[] {
  try {
    const files = JSON.parse(localStorage.getItem(selectionKey) || "[]");
    return Array.isArray(files) ? files.filter(file => typeof file?.path === "string" && typeof file?.name === "string").slice(0, 10000) : [];
  } catch { return []; }
}

function AdvancedMenu() {
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  return <>
    <Button endIcon={<ExpandMore />} aria-haspopup="menu" aria-expanded={Boolean(anchor)} onClick={event => setAnchor(event.currentTarget)}>Advanced</Button>
    <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
      <MenuItem component={Link} to="/intake/advanced" onClick={() => setAnchor(null)}>Advanced intake</MenuItem>
      <MenuItem component={Link} to="/admin/processors" onClick={() => setAnchor(null)}>Advanced setup</MenuItem>
    </Menu>
  </>;
}

export function AdvancedQueuePage() {
  return <QueuePage advanced />;
}

export function QueuePage({ advanced = false }: { advanced?: boolean }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const section = !advanced && params.get("tab") === "activity" ? "activity" : "add";
  const simple = !advanced && section === "add";
  const [files, setFiles] = useState<PickedFile[]>(restoreFiles);
  const [chosenFlow, setChosenFlow] = useState(() => sessionStorage.getItem("osii:intake-flow") || "");
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<{ severity: "error" | "success"; text: string } | null>(null);
  const setup = useQuery({ queryKey: quickStartKey, queryFn: getQuickStart, enabled: simple });
  const flows = useProcessingFlows(advanced);
  const selectedFlow = flows.data?.flows.find(flow => flow.id === chosenFlow)?.id
    ?? flows.data?.default_flow_id ?? "bundled";
  const canSelect = advanced || Boolean(setup.data?.ready && !setup.isError);
  const runs = useQuery({ queryKey: ["processing-runs"], queryFn: listProcessingRuns,
    refetchInterval: query => queuePollInterval(query.state.data?.runs) });
  const paths = files.map(file => file.path);
  const preview = useQuery({
    queryKey: ["intake", "selected-files", paths],
    queryFn: ({ signal }) => resolveIntake({ queue_paths: paths, include_subfolders: false, run_extraction: true, metadata_only: true }, signal),
    enabled: Boolean(files.length) && section === "add" && canSelect,
    retry: false, staleTime: Infinity, refetchOnWindowFocus: false,
  });
  const count = preview.data?.preview.matched_count ?? 0;

  useEffect(() => {
    try { localStorage.setItem(selectionKey, JSON.stringify(files)); }
    catch { setNotice({ severity: "error", text: "Browser storage is full. Keep this Intake tab open to retain the selection." }); }
  }, [files]);

  const onFlowChange = (id: string) => {
    setChosenFlow(id);
    try { sessionStorage.setItem("osii:intake-flow", id); } catch { /* The choice remains in memory. */ }
  };

  const onModelsUpdated = (value: QuickStart) => {
    client.setQueryData(quickStartKey, value);
    void client.invalidateQueries({ queryKey: ["admin"] });
    void client.invalidateQueries({ queryKey: ["intake", "readiness"] });
  };

  const queue = async () => {
    setStarting(true);
    setNotice(null);
    try {
      const run = await createProcessingRun({ queue_paths: paths, include_subfolders: false, workflow: "intake",
        processing_flow_id: advanced ? selectedFlow : "quick-start", extract_mode: "missing" });
      void client.invalidateQueries({ queryKey: ["processing-runs"] });
      if (advanced) {
        navigate(QUEUE_ACTIVITY_PATH);
      } else {
        navigate(buildRunRoute(run.id));
      }
    } catch (error) {
      if (!advanced) await setup.refetch();
      setNotice({ severity: "error", text: (error as Error).message });
    } finally {
      setStarting(false);
    }
  };

  return (
    <Stack spacing={2} sx={{ maxWidth: 1100, mx: "auto" }}>
      {advanced && <PageBreadcrumbs parents={[{ label: "Intake & Setup", to: "/intake" }]} current="Advanced intake" />}
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
        <Typography component="h1" variant="h5" fontWeight={700}>{advanced ? "Advanced intake" : "Intake & Setup"}</Typography>
        {advanced ? <Stack direction="row" gap={1}>
          <Button component={Link} to="/intake">Back to intake</Button>
          <Tooltip describeChild title="See what is running, review errors, or retry a failed stage">
            <Button component={Link} to={QUEUE_ACTIVITY_PATH}>Queue &amp; activity</Button>
          </Tooltip>
        </Stack> : <AdvancedMenu />}
      </Stack>
      {!advanced && <IntakeSections value={section}
        onChange={tab => setParams(tab === "activity" ? { tab: "activity" } : {})}
        activeCount={runs.data?.runs.filter(run => isActiveRun(run.status)).length ?? 0} />}
      {notice && <Alert severity={notice.severity}>{notice.text}</Alert>}
      {simple && <QuickStartModels data={setup.data} loading={setup.isPending} error={setup.error}
        onUpdate={onModelsUpdated} onRefresh={() => void setup.refetch()} />}
      {section === "add" && canSelect && <>
        <FileSelectionPanel files={files} onFiles={setFiles} title={advanced ? "1. Select files" : "2. Add documents"} />
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            {advanced && <>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Stack direction="row" alignItems="center">
                  <Typography variant="h6" fontWeight={700}>2. Process</Typography>
                  <Tooltip describeChild title="A flow chooses a reader for each file type and the processors that use saved text.">
                    <IconButton size="small" aria-label="What is a processing flow?"><HelpOutline fontSize="small" /></IconButton>
                  </Tooltip>
                </Stack>
                <Tooltip describeChild title="Edit and test this flow with a sample. Your file selection stays saved.">
                  <Button component={Link} to={"/admin/processing-flows/" + encodeURIComponent(selectedFlow) + "?from=intake"}>Edit selected flow</Button>
                </Tooltip>
              </Stack>
              <ProcessingFlowSelect value={selectedFlow} onChange={onFlowChange} />
              {flows.isError && <Alert severity="error">{flows.error.message}</Alert>}
            </>}
            {preview.isFetching && <Typography role="status" variant="body2">Checking access to selected files…</Typography>}
            {preview.isError && <Alert severity="error" action={<Button onClick={() => void preview.refetch()}>Retry file check</Button>}>{preview.error.message}</Alert>}
            {runs.data?.worker?.available === false && <Alert severity="warning">Worker unavailable. Queued files will wait.</Alert>}
            <Button variant="contained" disabled={!count || preview.isFetching || starting || (advanced && !flows.isSuccess)}
              onClick={() => void queue()}>
              {starting ? "Queueing…" : advanced ? `Queue ${count} ${count === 1 ? "file" : "files"}` : count ? `Process ${count} ${count === 1 ? "file" : "files"}` : "Process files"}
            </Button>
          </Stack>
        </Paper>
      </>}
      {section === "activity" && <>
        <ProcessingActivity recentRuns={runs.data?.runs ?? []} workerAvailable={runs.data?.worker?.available} />
        {runs.isError && <Alert severity="error">{runs.error.message}</Alert>}
      </>}
    </Stack>
  );
}
