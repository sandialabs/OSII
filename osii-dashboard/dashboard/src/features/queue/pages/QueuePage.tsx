import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, IconButton, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiJson } from "../../../api/client";
import { controlProcessingRun, createProcessingRun, getProcessingRunLogs, getIntakeReadiness, listProcessingRuns, recoverProcessingQueue, resolveIntake } from "../../../api/queue";
import type { ProcessingRun } from "../../../api/types";
import type { PickedFile } from "../../../components/discovery/LocationBrowser";
import { WorkflowProgress } from "../../../components/discovery/WorkflowProgress";
import { DiscoveryIntakePanel } from "../components/DiscoveryIntakePanel";
import { DiscoveryActivity, useDiscoveryRuns } from "../components/DiscoveryActivity";
import { IntakeSections } from "../components/IntakeSections";
import { ProcessingActivity, type ProcessingAction } from "../components/ProcessingActivity";
import { ProcessorStepControl } from "../components/ProcessorStepControl";

type Defaults = {preset: string; synthesize: boolean; build_embeddings: boolean; enrich: boolean; chunk_size: number; chunk_overlap: number; synthesizer: string; enricher: string; presets: {id: string; label: string; synthesize: boolean; build_embeddings: boolean; enrich: boolean}[]};
type TestReport = {tested_at: string; results: {processor: string; ok: boolean | null; detail?: string; diagnostics?: Record<string, unknown>}[]};
type Recipe = "text" | "search" | "summary-search" | "full" | "upgrade" | "index" | "summaries" | "custom";
const active = (status: string) => ["queued", "pending", "running", "pausing", "cancelling"].includes(status);

export function QueuePage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [section, setSection] = useState<"add" | "activity">(params.get("tab") === "activity" ? "activity" : "add");
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [selection, setSelection] = useState<number | null>(() => {
    const value = Number(localStorage.getItem("osii:last-intake-selection"));
    return Number.isInteger(value) && value > 0 ? value : null;
  });
  useEffect(() => {
    if (selection) localStorage.setItem("osii:last-intake-selection", String(selection));
    else localStorage.removeItem("osii:last-intake-selection");
  }, [selection]);
  const [recipe, setRecipe] = useState<Recipe>("text");
  const [extract, setExtract] = useState(true);
  const [synthesize, setSynthesize] = useState(false);
  const [embed, setEmbed] = useState(false);
  const [enrich, setEnrich] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [extractMode, setExtractMode] = useState<"missing" | "reprocess">("missing");
  const [policy, setPolicy] = useState<"auto" | "make_primary" | "save_variant">("auto");
  const [synthesizer, setSynthesizer] = useState("");
  const [enricher, setEnricher] = useState("");
  const [chunking, setChunking] = useState<"sentence_window" | "paragraph" | "window">("sentence_window");
  const [size, setSize] = useState(768);
  const [overlap, setOverlap] = useState(128);
  const [context, setContext] = useState("");
  const [collection, setCollection] = useState(false);
  const [collectionName, setCollectionName] = useState("");
  const [starting, setStarting] = useState(false);
  const [controlling, setControlling] = useState<string | null>(null);
  const [notice, setNotice] = useState<{severity: "error" | "info" | "success"; text: string} | null>(null);
  const [logId, setLogId] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [report, setReport] = useState<TestReport | null>(null);
  const [testError, setTestError] = useState("");
  const [help, setHelp] = useState(false);
  const initialized = useRef(false);
  const defaults = useQuery({queryKey: ["intake", "defaults"], queryFn: () => apiJson<Defaults>("/api/intake/defaults"), staleTime: Infinity});
  const readiness = useQuery({queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness, refetchInterval: 30_000});
  const runs = useQuery({queryKey: ["processing-runs"], queryFn: listProcessingRuns, refetchInterval: 2500});
  const scans = useDiscoveryRuns();
  const changeRecipe = (value: Recipe) => {
    initialized.current = true;
    setRecipe(value);
    if (value === "custom") return;
    setPolicy("auto"); setExtractMode(value === "upgrade" ? "reprocess" : "missing");
    const preset = defaults.data?.presets.find(item => item.id === value);
    setExtract(!["index", "summaries"].includes(value));
    setSynthesize(value === "summaries" || Boolean(preset?.synthesize));
    setEmbed(value === "index" || Boolean(preset?.build_embeddings));
    setEnrich(Boolean(preset?.enrich));
  };
  useEffect(() => {
    if (!defaults.data || initialized.current) return;
    const value = defaults.data;
    setSynthesizer(value.synthesizer); setEnricher(value.enricher);
    setSize(value.chunk_size); setOverlap(value.chunk_overlap);
    if (params.get("step") === "index") changeRecipe("index");
    else if (params.get("goal") === "reextract") changeRecipe("upgrade");
    else {
      setRecipe(value.preset as Recipe); setSynthesize(value.synthesize);
      setEmbed(value.build_embeddings); setEnrich(value.enrich); initialized.current = true;
    }
  }, [defaults.data]);
  const effectiveSynthesizer = synthesizer || readiness.data?.defaults.synthesizer || "";
  const effectiveEnricher = enricher || readiness.data?.defaults.enricher || "";
  const baseSelection = useMemo(() => ({inventory_selection_id: selection ?? undefined, queue_paths: selection ? [] : files.map(file => file.path), include_subfolders: false}), [files, selection]);
  // File metadata is requested once per explicit selection, never when a processing option changes.
  const preview = useQuery({queryKey: ["intake", "selected-files", baseSelection],
    queryFn: ({signal}) => resolveIntake({...baseSelection, run_extraction: true, synthesize: false, build_embeddings: false}, signal),
    enabled: section !== "activity" && Boolean(selection || files.length), retry: false, staleTime: Infinity, refetchOnWindowFocus: false});
  const plans = preview.data?.preview.extractor_plan ?? [];
  const count = preview.data?.preview.matched_count ?? 0;
  const methods = readiness.data?.extractors ?? [];
  const status = (name: string) => methods.find(method => method.id === name || method.aliases?.includes(name));
  const unavailable = plans.filter(plan => ![overrides[plan.extension] || plan.extractor, ...(overrides[plan.extension] ? [] : plan.fallbacks ?? [])].some(name => status(name)?.available));
  const embedder = readiness.data?.embedders.find(method => method.id === readiness.data?.defaults.embedder);
  const variantOnly = extract && policy === "save_variant";
  const options = {workflow: "intake", run_extraction: extract, extract_mode: extractMode, extractor_overrides: overrides, extraction_policy: policy,
    synthesizer_name: synthesize ? effectiveSynthesizer : null, build_embeddings: embed,
    chunking_method: chunking, chunk_size: size, chunk_overlap: overlap, enricher_name: enrich ? effectiveEnricher : null,
    expert_context: context.trim() || null, collection: collection ? {name: collectionName.trim()} : undefined};
  const signature = JSON.stringify({plans, overrides, extract, synthesize, embed, effectiveSynthesizer, recipe});
  const currentSignature = useRef(signature); currentSignature.current = signature;
  useEffect(() => { setReport(null); setTestError(""); }, [signature]);
  const testEndpoints = async () => {
    setTesting(true); setReport(null); setTestError("");
    const tested = signature;
    try {
      const names = extract ? [...new Set(plans.map(plan => overrides[plan.extension] || plan.extractor))] : [];
      const processors = names.map(name => ({name, kind: "extractor"}));
      if (synthesize && effectiveSynthesizer) processors.push({name: effectiveSynthesizer, kind: "synthesizer"});
      const result = await apiJson<TestReport>("/api/intake/preflight", {method: "POST", json: {processors, embed}});
      if (tested === currentSignature.current) setReport(result);
      else setTestError("Processing choices changed. Test again.");
    } catch (error) { setTestError((error as Error).message); }
    finally {setTesting(false);}
  };
  const showSection = (next: "add" | "activity") => {
    setNotice(null); setSection(next); setParams(next === "activity" ? {tab: "activity"} : {}, {replace: true});
  };
  const queue = async () => {
    setStarting(true); setNotice(null);
    try {
      const run = await createProcessingRun({...baseSelection, ...options});
      setLogId(null); showSection("activity");
      setNotice({severity: "success", text: `Queued ${run.resolved_count ?? count} ${(run.resolved_count ?? count) === 1 ? "file" : "files"}.`});
      await client.invalidateQueries({queryKey: ["processing-runs"]});
    } catch (error) {setNotice({severity: "error", text: (error as Error).message});}
    finally {setStarting(false);}
  };
  const control = async (run: ProcessingRun, action: ProcessingAction) => {
    if (action === "start") return;
    setControlling(`${run.id}:${action}`);
    try {
      await controlProcessingRun(run.id, action);
      await client.invalidateQueries({queryKey: ["processing-runs"]});
    } catch (error) {setNotice({severity: "error", text: (error as Error).message});}
    finally {setControlling(null);}
  };
  const logs = useQuery({queryKey: ["processing-runs", logId, "logs"], queryFn: () => getProcessingRunLogs(logId!), enabled: Boolean(logId) && section === "activity", refetchInterval: 2000});
  const activeCount = (runs.data?.runs.filter(run => active(run.status)).length ?? 0) + (scans.data?.filter(run => ["queued", "running"].includes(run.status)).length ?? 0);
  const blocked = !count || preview.isFetching || preview.isError || starting || testing || readiness.isLoading || runs.data?.worker?.available === false || readiness.data?.source?.osii_writable === false ||
    (!extract && !synthesize && !embed && !enrich) || (extract && unavailable.length > 0) || (synthesize && !effectiveSynthesizer) || (embed && !embedder?.available) ||
    (variantOnly && (synthesize || embed || enrich)) || (collection && !collectionName.trim()) || (embed && (size <= 0 || overlap < 0 || (chunking !== "paragraph" && overlap >= size))) || Boolean(report?.results.some(item => item.ok === false));
  return <Stack spacing={2.5} sx={{maxWidth: 1100, mx: "auto"}}>
    <Stack direction="row" alignItems="center" spacing={1}><Typography variant="h5" fontWeight={700}>Intake</Typography><IconButton aria-label="How Intake works" onClick={() => setHelp(true)}><HelpOutlineIcon /></IconButton></Stack>
    <WorkflowProgress readiness={readiness.data} checking={readiness.isLoading} failed={readiness.isError} onStep={step => {
      if (["extractor", "embedding", "language"].includes(step)) navigate(`/admin/processors?step=${step}`);
      else {showSection("add"); if (step === "index") changeRecipe("index");}
    }} />
    <IntakeSections value={section} onChange={showSection} activeCount={activeCount} />
    {notice && <Alert severity={notice.severity} onClose={() => setNotice(null)}>{notice.text}</Alert>}
    {runs.data?.worker?.available === false && <Alert severity="error" action={<Button onClick={async () => {
      try {await recoverProcessingQueue(); await runs.refetch();} catch (error) {setNotice({severity: "error", text: (error as Error).message});}
    }}>Check worker</Button>}>Worker unavailable. Queued files will wait.</Alert>}
    {section === "add" ? <>
      <DiscoveryIntakePanel selectedId={selection} onSelect={setSelection} directFiles={files} onFiles={setFiles} />
      <Paper variant="outlined" sx={{p: {xs: 2, sm: 3}}}><Stack spacing={2}>
        <Typography variant="h6" component="h2" fontWeight={750}>2. Choose processing</Typography>
        <TextField select size="small" label="Processing preset" value={recipe} onChange={event => changeRecipe(event.target.value as Recipe)}>
          {(defaults.data?.presets ?? [{id: "text", label: "Read text only"}]).map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
          <MenuItem value="upgrade">Upgrade extraction / OCR</MenuItem><MenuItem value="index">Index existing text</MenuItem><MenuItem value="summaries">Summarize existing text</MenuItem><MenuItem value="custom">Custom</MenuItem>
        </TextField>
        {defaults.isError && <Alert severity="error">Could not load processing defaults.</Alert>}
        <Stack spacing={1}>
          <FormControlLabel control={<Checkbox checked={extract} onChange={event => {setRecipe("custom"); setExtract(event.target.checked);}} />} label="Read text" />
          {extract && plans.map(plan => <TextField key={plan.extension} select size="small" label={`Reader for ${plan.extension}`} value={overrides[plan.extension] || ""} slotProps={{select: {displayEmpty: true}, inputLabel: {shrink: true}}} onChange={event => {
            const value = event.target.value;
            setOverrides(previous => {const next = {...previous}; if (value) next[plan.extension] = value; else delete next[plan.extension]; return next;});
            if (value) setExtractMode("reprocess");
          }}><MenuItem value="">File-type default ({status(plan.extractor)?.display_name || plan.extractor})</MenuItem>
            {methods.filter(method => {
              const extensions = method.descriptor?.capabilities?.file_extensions;
              return extensions?.includes("*") || extensions?.includes(plan.extension);
            }).map(method => <MenuItem key={method.id} value={method.id} disabled={!method.available}>{method.display_name}{!method.available ? " — unavailable" : ""}</MenuItem>)}
          </TextField>)}
          {extract && <TextField select size="small" label="Existing text" value={extractMode} onChange={event => setExtractMode(event.target.value as typeof extractMode)}>
            <MenuItem value="missing">Keep completed extraction</MenuItem><MenuItem value="reprocess">Read selected files again</MenuItem>
          </TextField>}
        </Stack>
        <Divider />
        <ProcessorStepControl label="Generate summaries" methodLabel="Summarizer" checked={synthesize} onChecked={value => {setRecipe("custom"); setSynthesize(value);}} method={effectiveSynthesizer} onMethod={setSynthesizer} options={readiness.data?.synthesizers ?? []} disabled={variantOnly} />
        <FormControlLabel control={<Checkbox checked={embed} disabled={variantOnly} onChange={event => {setRecipe("custom"); setEmbed(event.target.checked);}} />} label={`Build search embeddings${embedder ? ` · ${embedder.display_name}` : ""}`} />
        <Box component="details"><Box component="summary" sx={{cursor: "pointer", fontWeight: 600}}>Options</Box><Stack spacing={2} sx={{pt: 2}}>
          {extract && <TextField select size="small" label="New extraction" value={policy} onChange={event => {
            const value = event.target.value as typeof policy; setPolicy(value);
            if (value === "save_variant") {setSynthesize(false); setEmbed(false); setEnrich(false);}
          }}><MenuItem value="auto">Keep primary when adding a different reader</MenuItem><MenuItem value="make_primary">Use the new text as primary</MenuItem><MenuItem value="save_variant">Save another version only</MenuItem></TextField>}
          {embed && <Stack direction={{xs: "column", sm: "row"}} spacing={1}>
            <TextField select fullWidth size="small" label="Chunking" value={chunking} onChange={event => setChunking(event.target.value as typeof chunking)}><MenuItem value="sentence_window">Sentence windows</MenuItem><MenuItem value="paragraph">Paragraphs</MenuItem><MenuItem value="window">Fixed windows</MenuItem></TextField>
            <TextField type="number" size="small" label="Chunk characters" value={size} onChange={event => setSize(Number(event.target.value))} />
            <TextField type="number" size="small" label="Overlap" value={overlap} disabled={chunking === "paragraph"} onChange={event => setOverlap(Number(event.target.value))} />
          </Stack>}
          <ProcessorStepControl label="Run enrichment" methodLabel="Enricher" checked={enrich} onChecked={setEnrich} method={effectiveEnricher} onMethod={setEnricher} options={readiness.data?.enrichers ?? []} disabled={variantOnly} />
          <TextField multiline minRows={2} label="Expert guidance" value={context} onChange={event => setContext(event.target.value)} inputProps={{maxLength: 20_000}} />
          <FormControlLabel control={<Checkbox checked={collection} onChange={event => setCollection(event.target.checked)} />} label="Save selection as a collection" />
          {collection && <TextField size="small" label="Collection name" value={collectionName} onChange={event => setCollectionName(event.target.value)} />}
        </Stack></Box>
      </Stack></Paper>
      <Paper variant="outlined" sx={{p: {xs: 2, sm: 3}}}><Stack spacing={1.5}>
        <Typography variant="h6" component="h2" fontWeight={750}>3. Test & queue</Typography>
        {preview.isFetching && <LinearProgress aria-label="Checking selected files" />}
        {preview.isError && <Alert severity="error" action={<Button onClick={() => void preview.refetch()}>Retry selection check</Button>}>{preview.error.message}</Alert>}
        {readiness.isError && <Alert severity="error" action={<Button onClick={() => void readiness.refetch()}>Retry</Button>}>Endpoint status unavailable.</Alert>}
        {extract && unavailable.length > 0 && <Alert severity="error">Reader unavailable for {unavailable.map(plan => plan.extension).join(", ")}. Choose another reader or check Setup.</Alert>}
        {embed && embedder?.available === false && <Alert severity="warning" action={<Button onClick={() => navigate("/admin/processors?step=embedding")}>Setup</Button>}>Embedding endpoint unavailable. Choose Read text only to continue without embeddings.</Alert>}
        {testError && <Alert severity="error">{testError}</Alert>}
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Button variant="outlined" disabled={!count || testing || (!extract && !synthesize && !embed)} onClick={() => void testEndpoints()}>{testing ? "Testing sample…" : "Test selected endpoints"}</Button>
          {!report && <Chip size="small" label="Operation test not run" />}
          {report?.results.map((result, i) => <Chip key={i} color={result.ok === true ? "success" : result.ok === false ? "error" : "default"} label={`${result.processor}: ${result.ok === true ? "passed" : result.ok === false ? "failed" : "not tested"}`} />)}
        </Stack>
        {report && <details><summary>Test diagnostics · {new Date(report.tested_at).toLocaleTimeString()}</summary><Button size="small" onClick={() => void navigator.clipboard.writeText(JSON.stringify(report, null, 2))}>Copy test diagnostics</Button><Box component="pre" sx={{whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 300, overflow: "auto", fontSize: 12}}>{JSON.stringify(report, null, 2)}</Box></details>}
        <Stack direction="row" spacing={2} alignItems="center"><Button variant="contained" startIcon={<PlayArrowOutlinedIcon />} disabled={blocked} onClick={() => void queue()}>{starting ? "Queueing…" : `Queue ${count} ${count === 1 ? "file" : "files"}`}</Button><Typography variant="body2">{count ? "Only selected files will be processed." : "Select files to continue."}</Typography></Stack>
      </Stack></Paper>
    </> : <>
      {runs.isError && <Alert severity="error" action={<Button onClick={() => void runs.refetch()}>Retry</Button>}>Queue unavailable.</Alert>}
      <DiscoveryActivity />
      <ProcessingActivity recentRuns={runs.data?.runs ?? []} workerAvailable={runs.data?.worker?.available} selectedLogRunId={logId} setSelectedLogRunId={setLogId} controllingRun={controlling} controlRun={control} displayedLogLines={logs.data?.logs ?? runs.data?.runs.find(run => run.id === logId)?.logs ?? []} refreshLogs={() => void logs.refetch()} logError={logs.isError} />
    </>}
    <Dialog open={help} onClose={() => setHelp(false)} fullWidth maxWidth="sm"><DialogTitle>Choose files → choose processing → queue</DialogTitle><DialogContent><Stack spacing={2}>
      <Typography>Use this same workflow for new files and files already in the library. Completed text is reused unless you choose to read it again. Upgrade extraction adds OCR or another reader while preserving previous versions.</Typography>
      <Typography>Browse files in place, or upload copies. For large shares, open Scan a large folder or share to discover metadata gradually and select files found so far. Nothing is selected automatically.</Typography>
      <Typography>Test selected endpoints runs tiny sample operations, including the selected reader and model. It reads no library files; model-backed tests may use credits. A passed test applies to that sample and time.</Typography>
      <Typography>Queue & activity contains scanning, progress, failures, retry, and copyable diagnostics. Retrying failed work preserves completed results. Local extraction and keyword search work without a language model.</Typography>
    </Stack></DialogContent><DialogActions><Button onClick={() => setHelp(false)}>Close</Button></DialogActions></Dialog>
  </Stack>;
}
