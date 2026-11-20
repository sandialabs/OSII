import {useEffect, useState} from "react";
import {Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, MenuItem, Paper, Stack, TextField, Typography} from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import {useQueryClient} from "@tanstack/react-query";
import {apiJson} from "../../../api/client";
import {useProcessingFlows, type ProcessingFlow} from "../../queue/components/ProcessingFlowSelect";
import type {CapabilityReadiness} from "../../../api/types";
export function ProcessingFlows({readers, synthesizers, enrichers}: {readers: CapabilityReadiness[]; synthesizers: CapabilityReadiness[]; enrichers: CapabilityReadiness[]}) {
  useEffect(() => {if (window.location.hash === "#processing-flows") document.getElementById("processing-flows")?.scrollIntoView();}, []);
  const query = useProcessingFlows(); const client = useQueryClient();
  const [draft, setDraft] = useState<ProcessingFlow | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState(""); const [help, setHelp] = useState(false);
  const [report, setReport] = useState<unknown>(null);
  const test = async (id: string) => {
    setBusy(id); setError("");
    try {setReport(await apiJson(`/api/processing-flows/${id}/test`, {method: "POST"})); await client.invalidateQueries({queryKey: ["processing-flows"]});}
    catch (error) {setError((error as Error).message);} finally {setBusy(null);}
  };
  const save = async () => {
    if (!draft) return; setBusy(draft.id); setError("");
    try {await apiJson(`/api/processing-flows/${draft.id}`, {method: "PUT", json: draft}); setDraft(null); await test(draft.id);}
    catch (error) {setError((error as Error).message); setBusy(null);}
  };
  return <Paper id="processing-flows" variant="outlined" sx={{p: 2, scrollMarginTop: 80}}><Stack spacing={1.5}>
    <Stack direction="row" alignItems="center"><Typography variant="h6" fontWeight={700}>Processing flows</Typography><IconButton aria-label="About processing flows" onClick={() => setHelp(true)}><HelpOutlineIcon /></IconButton></Stack>
    <Typography variant="body2"><strong>All processes:</strong> extract → synthesize → enrich → embed</Typography>
    {query.isError && <Alert severity="error">{query.error.message}</Alert>}{error && <Alert severity="error">{error}</Alert>}
    {query.data?.flows.map(flow => <Box key={flow.id} sx={{borderTop: 1, borderColor: "divider", pt: 1.5}}><Stack spacing={0.75}>
      <Typography fontWeight={700}>{flow.name}</Typography>
      {flow.routes.map(route => <Typography key={route.name} variant="caption" sx={{overflowWrap: "anywhere"}}><strong>{route.extensions.length > 4 ? `${route.extensions.slice(0, 3).join(", ")} + ${route.extensions.length - 3} types` : route.extensions.join(", ")}:</strong> {[route.extractor, ...(route.fallbacks ?? [])].map(id => readers.find(item => item.id === id)?.display_name || id).join(" → ")}</Typography>)}
      <Typography variant="caption">Synthesis: {flow.synthesizer_name} · Enrichment: {flow.enricher_name}</Typography>
      <Stack direction="row" spacing={1} alignItems="center"><Button disabled={Boolean(busy)} onClick={() => setDraft(structuredClone(flow))}>Configure</Button><Button disabled={Boolean(busy)} onClick={() => void test(flow.id)}>{busy === flow.id ? "Testing sample…" : "Test sample"}</Button><Typography variant="caption" color={flow.test?.ok ? "success.main" : "text.secondary"}>{flow.test ? flow.test.ok ? "Sample passed" : "Sample had errors" : "Not tested"}</Typography></Stack>
    </Stack></Box>)}
    {report !== null && <details><summary style={{cursor: "pointer"}}>Sample test report</summary><Button onClick={() => void navigator.clipboard.writeText(JSON.stringify(report, null, 2))}>Copy test report</Button><Box component="pre" sx={{maxHeight: 300, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12}}>{JSON.stringify(report, null, 2)}</Box></details>}
  </Stack>
  <Dialog open={Boolean(draft)} onClose={() => setDraft(null)} maxWidth="md" fullWidth><DialogTitle>Configure flow</DialogTitle><DialogContent>{draft && <Stack spacing={2} sx={{pt: 1}}>
    <TextField label="Flow name" value={draft.name} onChange={event => setDraft({...draft, name: event.target.value})} />
    {draft.routes.map((route, index) => <Paper variant="outlined" key={index} sx={{p: 1.5}}><Stack spacing={1}><TextField size="small" label="File extensions (comma-separated)" value={route.extensions.join(", ")} onChange={event => setDraft({...draft, routes: draft.routes.map((item, i) => i === index ? {...item, extensions: event.target.value.split(",").map(value => value.trim())} : item)})} /><TextField select size="small" label="First reader" value={route.extractor} onChange={event => setDraft({...draft, routes: draft.routes.map((item, i) => i === index ? {...item, extractor: event.target.value} : item)})}>{[...new Set([route.extractor, ...readers.map(item => item.id)])].map(id => <MenuItem value={id} key={id} sx={{color: readers.find(item => item.id === id)?.available ? "text.primary" : "text.disabled"}}>{readers.find(item => item.id === id)?.display_name || id}</MenuItem>)}</TextField><TextField size="small" label="Fallback order (processor IDs, comma-separated)" value={(route.fallbacks ?? []).join(", ")} onChange={event => setDraft({...draft, routes: draft.routes.map((item, i) => i === index ? {...item, fallbacks: event.target.value.split(",").map(value => value.trim()).filter(Boolean)} : item)})} /></Stack></Paper>)}
    {([['synthesizer_name', 'Synthesizer', synthesizers], ['enricher_name', 'Enricher', enrichers]] as const).map(([key, label, choices]) => <TextField select key={key} size="small" label={label} value={draft[key]} onChange={event => setDraft({...draft, [key]: event.target.value})}>{[...new Set([draft[key], ...choices.map(item => item.id)])].filter(Boolean).map(id => <MenuItem key={id} value={id}>{choices.find(item => item.id === id)?.display_name || id}</MenuItem>)}</TextField>)}
  </Stack>}</DialogContent><DialogActions><Button onClick={() => setDraft(null)}>Cancel</Button><Button disabled={Boolean(busy)} onClick={() => {if (draft) setDraft({...draft, id: `custom-${Date.now()}`, name: `${draft.name} copy`});}}>Make a copy</Button><Button disabled={Boolean(busy)} onClick={() => void save()}>Save & test sample</Button></DialogActions></Dialog>
  <Dialog open={help} onClose={() => setHelp(false)} fullWidth maxWidth="sm"><DialogTitle>Processing flows</DialogTitle><DialogContent><Stack spacing={1.5}><Typography><strong>Configure and test here, then select the flow in Intake.</strong> Rules are checked top to bottom; the first matching extension selects a reader. Fallbacks are tried left to right after a failure. Put * last.</Typography><Typography><strong>Every flow runs all processes.</strong> Text extraction, synthesis, and enrichment run per file; embeddings follow. Tests use one page of the bundled Purcell PDF and tiny text samples, without changing your documents. A passed sample is evidence at that time, not a guarantee for every file or future endpoint availability.</Typography><Typography><strong>Saved in processors.toml.</strong> Flows are snapshotted into queued jobs, so editing a flow does not change a running job. Add an extractor by following docs/extending/processor-modules.md and implementing the Processor API in osii-processor-modules/.</Typography></Stack></DialogContent><DialogActions><Button onClick={() => setHelp(false)}>Close</Button></DialogActions></Dialog>
  </Paper>;
}
