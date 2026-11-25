import { useEffect, useState } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, LinearProgress, MenuItem, Paper, Stack, TextField, Tooltip, Typography } from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import ArrowDownwardOutlined from "@mui/icons-material/ArrowDownwardOutlined";
import ArrowUpwardOutlined from "@mui/icons-material/ArrowUpwardOutlined";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiJson } from "../../../api/client";
import { getSetupSummary } from "../../../api/queue";
import { PageBreadcrumbs } from "../../../components/workbench/PageBreadcrumbs";
import { useProcessingFlows, type ProcessingFlow } from "../../queue/components/ProcessingFlowSelect";
import { flowTestStatus, flowTestError, flowStepLabel, flowTestEntries, type FlowTestReport } from "../../../domain/processingFlowTests";
import type { CapabilityReadiness } from "../../../api/types";

const setupFlows = "/admin/processors#processing-flows";
export const flowPath = (id: string) => "/admin/processing-flows/" + encodeURIComponent(id);
const processorPath = (id: string, flow: string, fromIntake: boolean) => "/admin/processors/" + encodeURIComponent(id)
  + "?" + new URLSearchParams({ flow, ...(fromIntake ? { from: "intake" } : {}) });
type Rule = ProcessingFlow["routes"][number];

export function ProcessingFlows() {
  const query = useProcessingFlows();
  const [help, setHelp] = useState(false);
  useEffect(() => {
    if (window.location.hash === "#processing-flows") document.getElementById("processing-flows")?.scrollIntoView();
  }, []);
  return <Paper id="processing-flows" variant="outlined" sx={{ p: 2, scrollMarginTop: 80 }}>
    <Stack spacing={1}>
      <Stack direction="row" alignItems="center">
        <Typography component="h2" variant="h6" fontWeight={700}>Processing flows</Typography>
        <IconButton aria-label="About processing flows" onClick={() => setHelp(true)}><HelpOutlineIcon /></IconButton>
      </Stack>
      {query.isError && <Alert severity="error">{query.error.message}</Alert>}
      {query.data?.flows.map(flow => {
        const status = flowTestStatus(flow.test);
        return <Stack key={flow.id} direction="row" alignItems="center" justifyContent="space-between" gap={1} sx={{ borderTop: 1, borderColor: "divider", pt: 1 }}>
          <Stack><Typography fontWeight={700}>{flow.name}</Typography>
            {flow.description && <Typography variant="body2" color="text.secondary">{flow.description}</Typography>}
          </Stack>
          <Stack direction="row" alignItems="center" gap={1}>
            <Chip size="small" color={status.color} label={status.label} />
            <Button component={Link} to={flowPath(flow.id)} aria-label={"Edit " + flow.name}>Edit</Button>
          </Stack>
        </Stack>;
      })}
    </Stack>
  <Dialog open={help} onClose={() => setHelp(false)} fullWidth maxWidth="sm">
    <DialogTitle>Processing flows</DialogTitle>
    <DialogContent>
      <Stack spacing={1.5}>
        <Typography><strong>A processing flow is a named set of instructions for processing files.</strong> It chooses a reader for each file type. Summary, enrichment, and embeddings can use the saved text independently.</Typography>
        <Typography><strong>Set up here, then choose a flow in Intake.</strong> The first matching file-type rule wins. OSII tries backup readers in order if needed. Put the catch-all rule (<code>*</code>) last.</Typography>
        <Typography><strong>Test sample</strong> checks the processors on bundled examples. <strong>Results</strong> reopens the last test, and <strong>Copy report</strong> includes the technical details. Errors from your own files appear under <strong>Intake &amp; Setup → Queue &amp; activity</strong>.</Typography>
        <Typography>Flows are saved in <code>processors.toml</code>. Each queued job keeps the flow it started with. To add a reader, see <code>docs/extending/processor-modules.md</code>.</Typography>
      </Stack>
    </DialogContent>
    <DialogActions><Button onClick={() => setHelp(false)}>Close</Button></DialogActions>
  </Dialog>
  </Paper>;
}

export function ProcessingFlowPage() {
  const { flowId } = useParams();
  const [search] = useSearchParams();
  const fromIntake = search.get("from") === "intake";
  const flows = useProcessingFlows();
  const setup = useQuery({ queryKey: ["admin", "setup"], queryFn: getSetupSummary });
  const flow = flows.data?.flows.find(item => item.id === flowId);
  const readiness = setup.data?.readiness;
  return <Stack spacing={2} sx={{ maxWidth: 1000, mx: "auto" }}>
    <PageBreadcrumbs parents={[
      ...(fromIntake ? [{ label: "Advanced intake", to: "/intake/advanced" }] : [{ label: "Setup", to: "/admin/processors" }]),
      { label: "Processing flows", to: setupFlows },
    ]} current={flow?.name ?? "Flow"} />
    {(flows.isPending || setup.isPending) && <LinearProgress aria-label="Loading flow" />}
    {flows.isError || setup.isError ? <Alert severity="error">{flows.error?.message || setup.error?.message}</Alert>
      : flows.isSuccess && !flow ? <Alert severity="info">This flow is unavailable.</Alert> : null}
    {flow && readiness && <FlowEditor key={flow.id} flow={flow} readers={readiness.extractors}
      synthesizers={readiness.synthesizers} enrichers={readiness.enrichers} fromIntake={fromIntake} />}
  </Stack>;
}

function FlowEditor({ flow, readers, synthesizers, enrichers, fromIntake }: {
  flow: ProcessingFlow; readers: CapabilityReadiness[]; synthesizers: CapabilityReadiness[];
  enrichers: CapabilityReadiness[]; fromIntake: boolean;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(flow);
  const [ruleIndex, setRuleIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [reportOpen, setReportOpen] = useState(false);
  const [testFailure, setTestFailure] = useState<FlowTestReport>();
  const [copyStatus, setCopyStatus] = useState("");
  const activeReport = testFailure ?? flow.test;
  const changed = JSON.stringify(draft) !== JSON.stringify(flow);
  const processorLabel = (id?: string) => [...readers, ...synthesizers, ...enrichers].find(item => item.id === id || item.aliases?.includes(id || ""))?.display_name || id || "Endpoint";
  const copyReport = async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(activeReport, null, 2)); setCopyStatus("Report copied"); }
    catch { setCopyStatus("Clipboard unavailable. Select the technical details below to copy."); }
  };
  const save = async (id: string) => {
    setBusy(true); setError("");
    try {
      const saved = await apiJson<{ flow: ProcessingFlow; warnings: string[] }>("/api/processing-flows/" + encodeURIComponent(id), { method: "PUT", json: draft });
      setDraft(saved.flow); setWarnings(saved.warnings); setTestFailure(undefined);
      await client.invalidateQueries({ queryKey: ["processing-flows"] });
      if (id !== flow.id) navigate(flowPath(id) + (fromIntake ? "?from=intake" : ""));
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  };
  const test = async () => {
    setBusy(true); setError(""); setCopyStatus(""); setTestFailure(undefined);
    try {
      await apiJson<FlowTestReport>("/api/processing-flows/" + encodeURIComponent(flow.id) + "/test", { method: "POST" });
      await client.invalidateQueries({ queryKey: ["processing-flows"] });
      setDraft((client.getQueryData<{flows: ProcessingFlow[] }>(["processing-flows"])?.flows ?? []).find(item => item.id === flow.id) ?? draft);
    } catch (error) {
      setTestFailure({ ok: false, tested_at: new Date().toISOString(), results: [{ step: "test", ok: false, detail: (error as Error).message }] });
    } finally { setReportOpen(true); setBusy(false); }
  };
  const rule = draft.routes[ruleIndex];
  const changeRule = (change: Partial<Rule>) => setDraft(current => ({
    ...current, routes: current.routes.map((item, index) => index === ruleIndex ? { ...item, ...change } : item),
  }));
  const reorder = (offset: number) => {
    const routes = [...draft.routes];
    [routes[ruleIndex], routes[ruleIndex + offset]] = [routes[ruleIndex + offset], routes[ruleIndex]];
    setDraft({ ...draft, routes }); setRuleIndex(ruleIndex + offset);
  };
  const chain = [rule.extractor, ...(rule.fallbacks ?? [])];
  const capabilities = (id: string) => {
    const reader = readers.find(item => item.id === id || item.aliases?.includes(id));
    return reader?.descriptor?.capabilities ?? reader?.capabilities;
  };
  const supports = (id: string) => {
    const accepted = capabilities(id)?.file_extensions ?? [];
    return !accepted.length || accepted.includes("*") || rule.extensions.filter(Boolean).every(ext => accepted.includes(ext.toLowerCase()));
  };
  const configure = (id: string) => <Button size="small" component={Link} to={processorPath(id, flow.id, fromIntake)}>Settings</Button>;
  const status = flowTestStatus(activeReport);
  const selections = [
    ["synthesizer_name", "Summarize", synthesizers],
    ["enricher_name", "Enrich", enrichers],
  ] as const;
  return <Stack spacing={2}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
      <Typography component="h1" variant="h5" fontWeight={750}>{flow.name}</Typography>
      <Button component={Link} to={fromIntake ? "/intake/advanced" : setupFlows}>{fromIntake ? "Back to intake" : "Back to flows"}</Button>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {warnings.length > 0 && <Alert severity="warning">{warnings.join(" ")}</Alert>}
    <Stack direction={{ xs: "column", sm: "row" }} gap={1}>
      <TextField size="small" label="Flow name" value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} />
      <TextField size="small" fullWidth label="Description" value={draft.description ?? ""} onChange={event => setDraft({ ...draft, description: event.target.value })} />
    </Stack>
    <Paper component="section" variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Typography component="h2" variant="h6">Flowchart</Typography>
        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
          <TextField select size="small" label="File-type rule" value={ruleIndex} onChange={event => setRuleIndex(Number(event.target.value))} sx={{ minWidth: 190 }}>
            {draft.routes.map((item, index) => <MenuItem key={index} value={index}>{index + 1}. {item.name}</MenuItem>)}
          </TextField>
          <Tooltip title="Try this file-type rule sooner"><span><IconButton size="small" aria-label="Move rule earlier" disabled={ruleIndex === 0} onClick={() => reorder(-1)}><ArrowUpwardOutlined fontSize="small" /></IconButton></span></Tooltip>
          <Tooltip title="Try this file-type rule later"><span><IconButton size="small" aria-label="Move rule later" disabled={ruleIndex + 1 === draft.routes.length} onClick={() => reorder(1)}><ArrowDownwardOutlined fontSize="small" /></IconButton></span></Tooltip>
          <Button size="small" disabled={draft.routes.length >= 32} onClick={() => {
            const name = "rule-" + Date.now();
            setDraft({ ...draft, routes: [...draft.routes, { name, extensions: [], extractor: readers[0]?.id ?? "local.native-text" }] });
            setRuleIndex(draft.routes.length);
          }}>Add rule</Button>
          <Button size="small" disabled={draft.routes.length === 1} onClick={() => {
            setDraft({ ...draft, routes: draft.routes.filter((_, index) => index !== ruleIndex) });
            setRuleIndex(Math.max(0, ruleIndex - 1));
          }}>Remove rule</Button>
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} gap={1}>
          <TextField size="small" label="Rule name" value={rule.name} onChange={event => changeRule({ name: event.target.value })} />
          <TextField size="small" fullWidth label="Allowed file types" value={rule.extensions.join(",")} placeholder=".pdf, .txt"
            onChange={event => changeRule({ extensions: event.target.value.split(",").map(value => value.trim()) })} />
        </Stack>
        {chain.map((id, index) => <Stack direction="row" alignItems="center" gap={1} key={index}>
          <TextField select fullWidth size="small" label={index === 0 ? "Read text" : "If the previous reader fails"} value={id}
            onChange={event => index === 0 ? changeRule({ extractor: event.target.value })
              : changeRule({ fallbacks: chain.slice(1).map((item, i) => i === index - 1 ? event.target.value : item) })}>
            {[...new Set([id, ...readers.map(item => item.id)])].map(option => <MenuItem key={option} value={option}
              disabled={!supports(option) || (option !== id && chain.includes(option))}>{processorLabel(option)}</MenuItem>)}
          </TextField>
          {configure(id)}
          {index > 0 && <Button size="small" onClick={() => changeRule({ fallbacks: chain.slice(1).filter((_, i) => i !== index - 1) })}>Remove</Button>}
        </Stack>)}
        <Button size="small" sx={{ alignSelf: "start" }} disabled={!readers.some(item => supports(item.id) && !chain.includes(item.id))}
          onClick={() => {
            const reader = readers.find(item => supports(item.id) && !chain.includes(item.id));
            if (reader) changeRule({ fallbacks: [...chain.slice(1), reader.id] });
          }}>Add backup reader</Button>
        <Stack alignItems="center" spacing={0.5}>
          <ArrowDownwardOutlined color="action" />
          <Chip label="Saved text" variant="outlined" />
          <ArrowDownwardOutlined color="action" />
        </Stack>
        <Stack direction={{ xs: "column", md: "row" }} gap={1} aria-label="Processes that use saved text">
          {selections.map(([key, label, choices]) => <Paper key={key} variant="outlined" sx={{ p: 1, flex: 1, minWidth: 0 }}>
            <TextField select fullWidth size="small" label={label} value={draft[key]} onChange={event => setDraft({ ...draft, [key]: event.target.value })}>
              {[...new Set([draft[key], ...choices.map(item => item.id)])].map(id => <MenuItem key={id} value={id}>{processorLabel(id)}</MenuItem>)}
            </TextField>
            {configure(draft[key])}
          </Paper>)}
          <Paper variant="outlined" sx={{ p: 1, flex: 1 }}>
            <Typography fontWeight={650}>Build embeddings</Typography>
            <Button size="small" component={Link} to="/admin/processors#setup-model-connections">Embedding model</Button>
          </Paper>
        </Stack>
      </Stack>
    </Paper>
    <Stack direction="row" alignItems="center" flexWrap="wrap" gap={1}>
      <Button variant="contained" disabled={busy || !changed} onClick={() => void save(flow.id)}>Save flow</Button>
      <Button disabled={busy} onClick={() => void save("custom-" + Date.now())}>Save as new flow</Button>
      <Tooltip title={changed ? "Save changes before testing" : "Run each step on a bundled sample"}>
        <span><Button variant="outlined" disabled={busy || changed} onClick={() => void test()}>Test sample</Button></span>
      </Tooltip>
      <Chip size="small" color={status.color} label={busy ? "Working…" : status.label} />
      {activeReport && <Button onClick={() => { setCopyStatus(""); setReportOpen(true); }}>Results</Button>}
    </Stack>
  <Dialog open={reportOpen && Boolean(activeReport)} onClose={() => setReportOpen(false)} fullWidth maxWidth="md"><DialogTitle>{flow.name || "Flow"} · Test results</DialogTitle><DialogContent>{activeReport && <Stack spacing={2}>
    <Alert severity={activeReport.ok ? flowTestStatus(activeReport).color === "warning" ? "warning" : "success" : "error"}><strong>{activeReport.ok ? "The flow can process the sample." : "This flow needs attention."}</strong>{activeReport.ok && flowTestStatus(activeReport).color === "warning" ? " Each tested file-type rule had a working reader. See the failed reader checks below." : !activeReport.ok ? " Failed steps and their errors are shown below." : " All tested steps passed."}</Alert>
    {!activeReport.ok && activeReport.results.some(step => step.ok !== true && ["Generate summaries", "Build embeddings"].includes(flowStepLabel(step))) && <Button sx={{alignSelf: "start"}} component={Link} to="/admin/processors#setup-model-connections">Open model connections</Button>}
    <Typography variant="caption">{new Date(activeReport.tested_at).toLocaleString()} · {activeReport.sample || "Sample operation test"}</Typography>
    {flowTestEntries(activeReport).map(({step, index, attention}) => <Paper variant="outlined" sx={{p: attention ? 1.5 : 1}} key={index}><Stack spacing={1}>
      <Stack direction="row" justifyContent="space-between"><Typography fontWeight={700}>{index + 1}. {flowStepLabel(step)}</Typography><Chip size="small" color={step.ok === true ? "success" : "error"} label={step.ok === true ? "Passed" : step.ok === false ? "Failed" : "Not tested"} /></Stack>
      {!attention ? <Typography variant="caption" color="text.secondary">{step.attempts ? step.attempts.filter(attempt => attempt.ok).map(attempt => processorLabel(attempt.processor)).join(" → ") : processorLabel(step.processor)}{step.detail && step.detail !== "Tiny operation passed" ? ` · ${step.detail}` : ""}</Typography> : (step.attempts || [step]).map((attempt, i) => <Box key={i}><Typography variant="body2"><strong>{step.attempts ? `${i + 1}. ` : ""}{processorLabel(attempt.processor)}</strong>{step.attempts ? attempt.ok === true ? " · passed" : attempt.ok === false ? " · failed" : " · not tested" : ""}</Typography>{attempt.ok !== true && <Alert severity={step.ok ? "warning" : "error"} sx={{mt: 0.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere"}}>{flowTestError(attempt)}{(attempt.endpoint || attempt.diagnostics?.endpoint) && <Typography variant="caption" component="div" sx={{mt: 0.5}}>Service: {attempt.endpoint || attempt.diagnostics?.endpoint}</Typography>}</Alert>}{attempt.ok && attempt.detail && attempt.detail !== "Tiny operation passed" && <Typography variant="caption" color="text.secondary">{attempt.detail}</Typography>}</Box>)}
    </Stack></Paper>)}
    {copyStatus && <Typography role="status">{copyStatus}</Typography>}
    <Box component="details" open={copyStatus.startsWith("Clipboard unavailable") || undefined}><Box component="summary" sx={{cursor: "pointer"}}>Technical details</Box><Box component="pre" sx={{maxHeight: 350, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12}}>{JSON.stringify(activeReport, null, 2)}</Box></Box>
  </Stack>}</DialogContent><DialogActions><Button onClick={() => setReportOpen(false)}>Close</Button><Button variant="contained" onClick={() => void copyReport()}>Copy report</Button></DialogActions></Dialog>
  </Stack>;
}
