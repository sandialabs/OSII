import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import {
  Alert, Autocomplete, Button, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, Divider, IconButton, LinearProgress, MenuItem, Paper, Stack, TextField, Typography,
} from "@mui/material";
import { findCatalogFiles, getObjectExtractions, makeObjectExtractionPrimary } from "../../api/objects";
import HelpOutline from "@mui/icons-material/HelpOutline";
import { getIntakeReadiness, getProcessingRun } from "../../api/queue";
import type { ProcessingRun } from "../../api/types";
import { useObjectExtractionJob } from "../../hooks/useObjectExtractionJob";
import { useObject } from "../../hooks/useObject";
import { ocrSourceTypes, sourceCompatibility } from "../../domain/fileCompatibility";
import { ocrWorkbench } from "../../domain/workbench";
import { LocationBrowser, type PickedFile } from "../../components/discovery/LocationBrowser";
import { LibraryFlow } from "../../components/workbench/LibraryFlow";
import { buildFileRoute } from "../../utils/routes";
import { DocumentReadingPane } from "../files/components/DocumentReadingPane";
import { ExtractionVersions } from "../files/components/ExtractionVersions";
import { ExtractionArtifacts } from "../files/components/ExtractionArtifacts";

const liveStatuses = ["pending", "queued", "running", "pausing", "cancelling"];
const runLabels: Record<string, string> = {
  pending: "Queued", queued: "Queued", running: "Running OCR", done: "OCR saved",
  error: "OCR failed", paused: "Paused", cancelled: "Cancelled",
  pausing: "Pausing", cancelling: "Cancelling",
};

export function OcrWorkbenchPage() {
  const [params, setParams] = useSearchParams();
  const [picked, setPicked] = useState<PickedFile | undefined>();
  const [browseOpen, setBrowseOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [fileSearch, setFileSearch] = useState("");
  const runId = params.get("run_id") ?? "";
  const run = useQuery({
    queryKey: ["processing-runs", "detail", runId],
    queryFn: ({ signal }) => getProcessingRun(runId, signal),
    enabled: Boolean(runId),
    refetchInterval: query => liveStatuses.includes(query.state.data?.status ?? "") ? 1_500 : false,
  });
  const runItem = run.data?.items?.[0];
  const fileId = params.get("file_id") ?? (runItem?.status === "done" ? runItem.file_id : "") ?? "";
  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness, staleTime: 30_000 });
  const files = useQuery({
    queryKey: ["ocr", "catalog", fileSearch],
    queryFn: ({ signal }) => findCatalogFiles(fileSearch, signal),
    enabled: pickerOpen,
    staleTime: 30_000,
  });
  const current = useObject(fileId, Boolean(fileId));
  const methods = (readiness.data?.extractors ?? []).flatMap(method => {
    const types = ocrSourceTypes(method);
    return types ? [{ ...method, types }] : [];
  });
  const readyFile = current.data?.meta.file;
  const file = readyFile ?? (picked ? { filename: picked.name, mime: picked.mime ?? null } : undefined);
  const compatible = (candidate: { filename?: string | null; mime?: string | null }) =>
    methods.some(method => sourceCompatibility(candidate, method.types) === "supported");
  const options = (files.data?.items ?? []).filter(compatible).map(item => ({
    id: item.file_id,
    label: item.source_relpath || item.filename || item.file_id,
  }));
  const selected = options.find(item => item.id === fileId) ?? (fileId ? { id: fileId, label: readyFile?.filename ?? fileId } : null);

  return (
    <Stack spacing={2.5} sx={{ maxWidth: 1200, mx: "auto" }}>
      <Stack spacing={0.5}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography component="h1" variant="h4" fontWeight={750}>OCR Workbench</Typography>
          <IconButton aria-label="About OCR Workbench" onClick={() => setHelpOpen(true)}><HelpOutline /></IconButton>
        </Stack>
        <Typography color="text.secondary">One file · Recognize text in a PDF or image</Typography>
        <LibraryFlow {...ocrWorkbench.flow} />
      </Stack>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <Autocomplete options={options} value={selected} filterOptions={items => items}
              isOptionEqualToValue={(left, right) => left.id === right.id}
              loading={files.isFetching || readiness.isPending}
              open={pickerOpen} onOpen={() => setPickerOpen(true)}
              onClose={() => { setPickerOpen(false); setFileSearch(""); }}
              onInputChange={(_, value, reason) => { if (reason === "input" || reason === "clear") setFileSearch(value.trim()); }}
              noOptionsText={files.data?.next_cursor ? "Search by filename to narrow the results" : "No compatible files found"}
              onChange={(_, item) => { setPicked(undefined); setParams(item ? { file_id: item.id } : {}); }}
              renderInput={input => <TextField {...input} label="Choose a library file" size="small" />}
              sx={{ flex: 1 }}
            />
            <Button variant="outlined" onClick={() => setBrowseOpen(true)}>Browse for a file</Button>
          </Stack>
          {picked && !fileId && <Typography fontWeight={650}>{picked.name}</Typography>}
          <LocationBrowser open={browseOpen} singleFile selected={picked ? [picked] : []}
            onClose={() => setBrowseOpen(false)}
            onFiles={items => { setPicked(items[0]); setParams({}); setBrowseOpen(false); }}
          />
          {files.isError && <Alert severity="warning" action={<Button onClick={() => void files.refetch()}>Retry</Button>}>Could not load library files.</Alert>}
          {readiness.isError && <Alert severity="error" action={<Button onClick={() => void readiness.refetch()}>Retry</Button>}>Could not check OCR methods.</Alert>}
          {readiness.isSuccess && !methods.length && <Alert severity="info" action={<Button component={Link} to="/admin/processors">Setup</Button>}>No OCR method is configured.</Alert>}
          {fileId && current.isPending && <LinearProgress aria-label="Loading selected file" />}
          {fileId && current.isError && <Alert severity="error">Could not load the selected file. {current.error.message}</Alert>}
          {(file || runId) && <OcrDocument key={fileId || picked?.path || runId} fileId={fileId} file={file}
            run={run} picked={fileId ? undefined : picked} sourceActive={current.data?.artifact_summary.actions.source_is_active ?? Boolean(picked)}
            methods={methods.filter(method => file && sourceCompatibility(file, method.types) === "supported")}
            catalogLoaded={readiness.isSuccess && methods.length > 0}
          />}
        </Stack>
      </Paper>
      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} aria-labelledby="ocr-help-title">
        <DialogTitle id="ocr-help-title">About OCR Workbench</DialogTitle>
        <DialogContent><Typography><strong>OCR saves a text version.</strong> Existing primary text stays in use until you choose Make primary. For a new file, its first extraction is primary. Available formats depend on the selected method.</Typography></DialogContent>
        <DialogActions><Button onClick={() => setHelpOpen(false)}>Close</Button></DialogActions>
      </Dialog>
    </Stack>
  );
}

function OcrDocument({ fileId, file, picked, run, sourceActive, methods, catalogLoaded }: {
  fileId: string;
  file?: { filename: string; mime: string | null };
  picked?: PickedFile;
  run: UseQueryResult<ProcessingRun>;
  sourceActive: boolean;
  methods: { id: string; display_name: string; available: boolean; detail: string }[];
  catalogLoaded: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const [methodId, setMethodId] = useState("");
  const [page, setPage] = useState(1);
  const [segmentId, setSegmentId] = useState<string | null>(null);
  const client = useQueryClient();
  const runId = params.get("run_id") ?? "";
  const variantId = params.get("extraction_id") ?? "";
  const method = methods.find(item => item.id === methodId && item.available) ?? methods.find(item => item.available);
  const versions = useQuery({ queryKey: ["objects", fileId, "extractions"], queryFn: () => getObjectExtractions(fileId), enabled: Boolean(fileId) });
  const refreshFile = () => Promise.all([
    client.invalidateQueries({ queryKey: ["objects", fileId] }),
    client.invalidateQueries({ queryKey: ["objects", "detail", fileId] }),
    client.invalidateQueries({ queryKey: ["products", "list", fileId] }),
  ]);
  const queue = useObjectExtractionJob(fileId, picked);
  const promote = useMutation({
    mutationFn: (id: string) => makeObjectExtractionPrimary(fileId, id),
    onSuccess: refreshFile,
  });
  const status = run.data?.status;
  const running = queue.isPending || Boolean(runId && (run.isPending || liveStatuses.includes(status ?? "") || status === "paused"));
  const runItem = run.data?.items?.[0];
  const runError = runItem?.error || run.data?.error;
  const inspected = variantId || runItem?.extraction_variant_id || "";
  const activeVariant = versions.data?.variants.find(version => version.id === inspected);

  useEffect(() => {
    if (fileId && (status === "done" || status === "error")) {
      void client.invalidateQueries({ queryKey: ["objects", fileId, "extractions"] });
      void client.invalidateQueries({ queryKey: ["objects", "detail", fileId] });
      void client.invalidateQueries({ queryKey: ["objects", fileId, "texts"] });
      void client.invalidateQueries({ queryKey: ["objects", fileId, "preferred-text"] });
      void client.invalidateQueries({ queryKey: ["scopes", "summaries"] });
      void client.invalidateQueries({ queryKey: ["ocr", "catalog"] });
      void client.invalidateQueries({ queryKey: ["workbench-home"] });
    }
  }, [fileId, client, runId, status]);

  const inspect = (id: string) => {
    setPage(1);
    setSegmentId(null);
    const next = new URLSearchParams(params);
    next.set("extraction_id", id);
    setParams(next);
  };

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
        {methods.length > 0 && <TextField select label="OCR method" size="small" value={method?.id ?? ""} sx={{ flex: 1 }} disabled={running || !method}
          onChange={event => setMethodId(event.target.value)}>
          <MenuItem value="" disabled>Choose a ready method</MenuItem>
          {methods.map(item => <MenuItem key={item.id} value={item.id} disabled={!item.available}>{item.display_name}{item.available ? "" : " · unavailable"}</MenuItem>)}
        </TextField>}
        <Button variant="contained" disabled={!method || !sourceActive || running || run.isError}
          onClick={() => {
            if (!method) return;
            queue.mutate({ extractor_name: method.id, extraction_policy: "save_variant" }, {
              onSuccess: job => {
                setPage(1);
                setSegmentId(null);
                client.setQueryData(["processing-runs", "detail", job.id], job);
                setParams(fileId ? { file_id: fileId, run_id: job.id } : { run_id: job.id });
              },
            });
          }}>{queue.isPending ? "Queueing…" : "Run OCR"}</Button>
        {fileId && <Button component={Link} to={buildFileRoute({ fileId })}>View file products</Button>}
      </Stack>
      {file && !sourceActive && <Alert severity="warning">Original file is unavailable.</Alert>}
      {file && catalogLoaded && !methods.length && <Alert severity="info">No OCR method accepts this file type.</Alert>}
      {methods.length > 0 && !method && <Alert severity="warning" action={<Button component={Link} to="/admin/processors">Setup</Button>}>{methods[0].detail || "No compatible OCR method is ready."}</Alert>}
      {queue.isError && <Alert severity="error">{queue.error.message}</Alert>}
      {run.isError && <Alert severity="warning" action={<Button onClick={() => void run.refetch()}>Retry status</Button>}>Could not check this OCR run.</Alert>}
      {runId && status && <Stack spacing={1}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography role="status" fontWeight={650}>{runError ? "OCR failed" : runLabels[status] ?? status}</Typography>
          <Button component={Link} to="/intake?tab=activity">Intake & Queue</Button>
        </Stack>
        {liveStatuses.includes(status) && <LinearProgress aria-label="OCR progress" />}
        {runError && <Alert severity="error" sx={{ overflowWrap: "anywhere" }}>{runError}</Alert>}
      </Stack>}
      {fileId && <>
        <Divider />
        <Typography component="h2" variant="h6" fontWeight={700}>Text versions</Typography>
        {versions.isPending && <CircularProgress size={20} aria-label="Loading text versions" />}
        {versions.isError && <Alert severity="error" action={<Button onClick={() => void versions.refetch()}>Retry</Button>}>Could not load text versions.</Alert>}
        {versions.isSuccess && !versions.data.variants.length && <Typography color="text.secondary">No versions saved yet.</Typography>}
        <ExtractionVersions variants={versions.data?.variants ?? []} onInspect={inspect} onPromote={id => {
          if (window.confirm("Make this the primary text? Existing summaries and the search index may need refreshing.")) promote.mutate(id);
        }} promoting={promote.isPending || running} />
        {promote.isError && <Alert severity="error">{promote.error.message}</Alert>}
      </>}
      {activeVariant && file && <Stack component="section" aria-label="Extraction preview" spacing={2} key={activeVariant.id}>
        <Typography component="h2" variant="h6" fontWeight={700}>Source and text · {activeVariant.extractor.name}</Typography>
        <DocumentReadingPane fileId={fileId} mime={file.mime} versionId={activeVariant.id} mode="split" page={page} segmentId={segmentId}
          readOnly onPageChange={setPage} onJumpToSource={target => { if (target.page) setPage(target.page); setSegmentId(target.segmentId ?? null); }} />
        <ExtractionArtifacts fileId={fileId} variantId={activeVariant.id} />
      </Stack>}
    </Stack>
  );
}
