import {useEffect, useState} from "react";
import {Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, MenuItem, Paper, Stack, TextField, Typography} from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import {useQueryClient} from "@tanstack/react-query";
import {apiJson} from "../../../api/client";
import {useProcessingFlows, type ProcessingFlow} from "../../queue/components/ProcessingFlowSelect";
import {flowTestStatus, flowTestError, flowStepLabel, flowTestEntries, type FlowTestReport} from "../../../domain/processingFlowTests";
import type {CapabilityReadiness} from "../../../api/types";
export function ProcessingFlows({readers, synthesizers, enrichers}: {readers: CapabilityReadiness[]; synthesizers: CapabilityReadiness[]; enrichers: CapabilityReadiness[]}) {
  useEffect(() => {if (window.location.hash === "#processing-flows") document.getElementById("processing-flows")?.scrollIntoView();}, []);
  const query = useProcessingFlows(); const client = useQueryClient();
  const [ruleIndex, setRuleIndex] = useState(0);
  const [draft, setDraft] = useState<ProcessingFlow | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState(""); const [help, setHelp] = useState(false);
  const [reports, setReports] = useState<Record<string, FlowTestReport>>({});
  const [viewReport, setViewReport] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const activeFlow = query.data?.flows.find(flow => flow.id === viewReport);
  const activeReport = viewReport ? (reports[viewReport]?.fingerprint === activeFlow?.fingerprint ? reports[viewReport] : activeFlow?.test) : null;
  const processorLabel = (id?: string) => [...readers, ...synthesizers, ...enrichers].find(item => item.id === id || item.aliases?.includes(id || ""))?.display_name || id || "Endpoint";
  const copyReport = async () => {
    try {await navigator.clipboard.writeText(JSON.stringify(activeReport, null, 2)); setCopyStatus("Report copied");}
    catch {setCopyStatus("Clipboard unavailable. Select the technical details below to copy.");}
  };
  const test = async (id: string) => {
    setBusy(id); setError("");
    try {
      const report = await apiJson<FlowTestReport>(`/api/processing-flows/${id}/test`, {method: "POST"});
      setReports(current => ({...current, [id]: report})); setCopyStatus(""); setViewReport(id);
      await client.invalidateQueries({queryKey: ["processing-flows"]});
    }
    catch (error) {
      const failure: FlowTestReport = {ok: false, tested_at: new Date().toISOString(), sample: "Test request did not complete", fingerprint: query.data?.flows.find(flow => flow.id === id)?.fingerprint,
        results: [{processor: "OSII Setup", step: "test", ok: false, detail: (error as Error).message}]};
      setReports(current => ({...current, [id]: failure})); setViewReport(id);
    } finally {setBusy(null);}
  };
  const save = async () => {
    if (!draft) return; setBusy(draft.id); setError("");
    try {await apiJson(`/api/processing-flows/${draft.id}`, {method: "PUT", json: draft}); setReports(current => {const next = {...current}; delete next[draft.id]; return next;}); setDraft(null); await test(draft.id);}
    catch (error) {setError((error as Error).message); setBusy(null);}
  };
  return <Paper id="processing-flows" variant="outlined" sx={{p: 2, scrollMarginTop: 80}}><Stack spacing={1.5}>
    <Stack direction="row" alignItems="center"><Typography variant="h6" fontWeight={700}>Processing flows</Typography><IconButton aria-label="About processing flows" onClick={() => setHelp(true)}><HelpOutlineIcon /></IconButton></Stack>
    {query.isError && <Alert severity="error">{query.error.message}</Alert>}{error && !draft && <Alert severity="error">{error}</Alert>}
    {query.data?.flows.map(flow => {
      const report = reports[flow.id]?.fingerprint === flow.fingerprint ? reports[flow.id] : flow.test;
      const status = flowTestStatus(report);
      return <Box key={flow.id} sx={{borderTop: 1, borderColor: "divider", pt: 1.5}}><Stack direction={{xs: "column", sm: "row"}} spacing={1} justifyContent="space-between" alignItems={{sm: "center"}}>
        <Stack spacing={0.5}><Typography fontWeight={700}>{flow.name}</Typography><Chip size="small" sx={{alignSelf: "start"}} color={status.color} label={busy === flow.id ? "Testing…" : status.label} /></Stack>
        <Stack direction="row" spacing={1}>{flow.editable !== false && <Button disabled={Boolean(busy)} onClick={() => {setRuleIndex(0); setDraft(structuredClone(flow));}}>Edit flow</Button>}<Button variant="outlined" disabled={Boolean(busy)} onClick={() => void test(flow.id)}>Test sample</Button>{report && <Button color={report.ok ? "primary" : "error"} onClick={() => {setCopyStatus(""); setViewReport(flow.id);}}>{report.ok ? "View results" : "View errors"}</Button>}</Stack>
      </Stack></Box>;
    })}

  </Stack>
  <Dialog open={Boolean(viewReport && activeReport)} onClose={() => setViewReport(null)} fullWidth maxWidth="md"><DialogTitle>{activeFlow?.name || "Flow"} · Test results</DialogTitle><DialogContent>{activeReport && <Stack spacing={2}>
    <Alert severity={activeReport.ok ? flowTestStatus(activeReport).color === "warning" ? "warning" : "success" : "error"}><strong>{activeReport.ok ? "The flow can process the sample." : "This flow needs attention."}</strong>{activeReport.ok && flowTestStatus(activeReport).color === "warning" ? " A fallback reader recovered from an earlier failure." : !activeReport.ok ? " Failed steps and their errors are shown below." : " All tested steps passed."}</Alert>
    {!activeReport.ok && activeReport.results.some(step => step.ok !== true && ["Generate summaries", "Build embeddings"].includes(flowStepLabel(step))) && <Button sx={{alignSelf: "start"}} onClick={() => {setViewReport(null); document.getElementById("setup-model-connections")?.scrollIntoView({behavior: "smooth"});}}>Open model connections</Button>}
    <Typography variant="caption">{new Date(activeReport.tested_at).toLocaleString()} · {activeReport.sample || "Sample operation test"}</Typography>
    {flowTestEntries(activeReport).map(({step, index, attention}) => <Paper variant="outlined" sx={{p: attention ? 1.5 : 1}} key={index}><Stack spacing={1}>
      <Stack direction="row" justifyContent="space-between"><Typography fontWeight={700}>{index + 1}. {flowStepLabel(step)}</Typography><Chip size="small" color={step.ok === true ? "success" : "error"} label={step.ok === true ? "Passed" : step.ok === false ? "Failed" : "Not tested"} /></Stack>
      {!attention ? <Typography variant="caption" color="text.secondary">{step.attempts ? step.attempts.filter(attempt => attempt.ok).map(attempt => processorLabel(attempt.processor)).join(" → ") : processorLabel(step.processor)}{step.detail && step.detail !== "Tiny operation passed" ? ` · ${step.detail}` : ""}</Typography> : (step.attempts || [step]).map((attempt, i) => <Box key={i}><Typography variant="body2"><strong>{step.attempts ? `${i + 1}. ` : ""}{processorLabel(attempt.processor)}</strong>{step.attempts ? attempt.ok ? " · passed" : step.ok ? " · recovered by a fallback" : " · failed" : ""}</Typography>{attempt.ok !== true && <Alert severity={step.ok ? "warning" : "error"} sx={{mt: 0.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere"}}>{flowTestError(attempt)}{(attempt.endpoint || attempt.diagnostics?.endpoint) && <Typography variant="caption" component="div" sx={{mt: 0.5}}>Service: {attempt.endpoint || attempt.diagnostics?.endpoint}</Typography>}</Alert>}{attempt.ok && attempt.detail && attempt.detail !== "Tiny operation passed" && <Typography variant="caption" color="text.secondary">{attempt.detail}</Typography>}</Box>)}
    </Stack></Paper>)}
    {copyStatus && <Typography role="status">{copyStatus}</Typography>}
    <Box component="details" open={copyStatus.startsWith("Clipboard unavailable") || undefined}><Box component="summary" sx={{cursor: "pointer"}}>Technical details</Box><Box component="pre" sx={{maxHeight: 350, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12}}>{JSON.stringify(activeReport, null, 2)}</Box></Box>
  </Stack>}</DialogContent><DialogActions><Button onClick={() => setViewReport(null)}>Close</Button><Button variant="contained" onClick={() => void copyReport()}>Copy report</Button></DialogActions></Dialog>
  <Dialog open={Boolean(draft)} onClose={() => setDraft(null)} maxWidth="md" fullWidth><DialogTitle>Configure flow</DialogTitle><DialogContent>{draft && <Stack spacing={2} sx={{pt: 1}}>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField label="Flow name" value={draft.name} onChange={event => setDraft({...draft, name: event.target.value})} />
    <TextField select size="small" label="File-type rule · first match wins" value={ruleIndex} onChange={event => setRuleIndex(Number(event.target.value))}>{draft.routes.map((route, index) => <MenuItem key={index} value={index}>{index + 1}. {route.extensions.includes("*") ? "Other file types" : `${route.extensions.length} file types · ${[".pdf", ".txt", ".docx", ".png", ...route.extensions].filter((extension, i, values) => route.extensions.includes(extension) && values.indexOf(extension) === i).slice(0, 3).join(", ")}`}</MenuItem>)}</TextField>
    {draft.routes[ruleIndex] && (() => {
      const route = draft.routes[ruleIndex];
      const changeRoute = (change: Partial<typeof route>) => setDraft({...draft, routes: draft.routes.map((item, i) => i === ruleIndex ? {...item, ...change} : item)});
      const chain = [route.extractor, ...(route.fallbacks || [])];
      return <Stack spacing={1}>
        <TextField size="small" label="File types" value={route.extensions.join(", ")} onChange={event => changeRoute({extensions: event.target.value.split(",").map(value => value.trim())})} />
        {chain.map((value, index) => <Stack direction="row" spacing={1} key={index}><TextField select fullWidth size="small" label={index === 0 ? "1. First reader" : `${index + 1}. If the previous reader fails`} value={value} onChange={event => index === 0 ? changeRoute({extractor: event.target.value}) : changeRoute({fallbacks: (route.fallbacks || []).map((id, i) => i === index - 1 ? event.target.value : id)})}>{[...new Set([value, ...readers.map(item => item.id)])].filter(Boolean).map(id => {
          const reader = readers.find(item => item.id === id || item.aliases?.includes(id));
          const extensions = reader?.descriptor?.capabilities?.file_extensions;
          const incompatible = Boolean(extensions?.length && !extensions.includes("*") && route.extensions.some(extension => !extensions.includes(extension)));
          return <MenuItem value={id} key={id} disabled={incompatible || (chain.includes(id) && id !== value)} sx={{color: reader?.available ? "text.primary" : "text.disabled"}}>{reader?.display_name || id}{reader && !reader.available ? " · unavailable" : ""}</MenuItem>;
        })}</TextField>{index > 0 && <Button size="small" onClick={() => changeRoute({fallbacks: (route.fallbacks || []).filter((_, i) => i !== index - 1)})}>Remove</Button>}</Stack>)}
        <Button sx={{alignSelf: "start"}} disabled={!readers.some(item => !chain.includes(item.id) && (item.descriptor?.capabilities?.file_extensions?.includes("*") || route.extensions.every(extension => item.descriptor?.capabilities?.file_extensions?.includes(extension))))} onClick={() => {
          const next = readers.find(item => !chain.includes(item.id) && (item.descriptor?.capabilities?.file_extensions?.includes("*") || route.extensions.every(extension => item.descriptor?.capabilities?.file_extensions?.includes(extension))));
          if (next) changeRoute({fallbacks: [...(route.fallbacks || []), next.id]});
        }}>Add fallback reader</Button>
      </Stack>;
    })()}
    {([['synthesizer_name', 'Synthesizer', synthesizers], ['enricher_name', 'Enricher', enrichers]] as const).map(([key, label, choices]) => <TextField select key={key} size="small" label={label} value={draft[key]} onChange={event => setDraft({...draft, [key]: event.target.value})}>{[...new Set([draft[key], ...choices.map(item => item.id)])].filter(Boolean).map(id => <MenuItem key={id} value={id}>{choices.find(item => item.id === id)?.display_name || id}</MenuItem>)}</TextField>)}
  </Stack>}</DialogContent><DialogActions><Button onClick={() => setDraft(null)}>Cancel</Button><Button disabled={Boolean(busy)} onClick={() => {if (draft) setDraft({...draft, id: `custom-${Date.now()}`, name: `${draft.name} copy`});}}>Make a copy</Button><Button disabled={Boolean(busy)} onClick={() => void save()}>Save & test sample</Button></DialogActions></Dialog>
  <Dialog open={help} onClose={() => setHelp(false)} fullWidth maxWidth="sm"><DialogTitle>Processing flows</DialogTitle><DialogContent><Stack spacing={1.5}><Typography><strong>Configure and test here, then select the flow in Intake.</strong> Rules are checked top to bottom; the first matching extension selects a reader. Fallbacks are tried left to right after a failure. Put * last.</Typography><Typography>Text extraction, synthesis, and enrichment run per file. Flows that include embeddings use the configured model. Tests use the text-layer page from the bundled NIST cloud-computing PDF and tiny text samples, without changing your documents. A passed sample is evidence at that time, not a guarantee for every file or future endpoint availability.</Typography><Typography><strong>Saved in processors.toml.</strong> Flows are snapshotted into queued jobs, so editing a flow does not change a running job. Add an extractor by following docs/extending/processor-modules.md and implementing the Processor API in osii-processor-modules/.</Typography></Stack></DialogContent><DialogActions><Button onClick={() => setHelp(false)}>Close</Button></DialogActions></Dialog>
  </Paper>;
}
