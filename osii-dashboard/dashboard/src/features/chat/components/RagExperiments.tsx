import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { RagComparison, RagProfiles, RagTrace } from "../types";

export function RagProfileControls({ catalog, selected, onSelect, comparison, onComparison, busy, onCompare, canCompare }: {
  catalog: RagProfiles; selected: string; onSelect: (id: string) => void;
  comparison: string[]; onComparison: (ids: string[]) => void; busy: boolean; onCompare: () => void; canCompare: boolean;
}) {
  return <Stack spacing={1.5}>
    <Typography variant="subtitle2">RAG experiments · Chat model: {catalog.chat_model}</Typography>
    <TextField select label="RAG profile" value={selected} disabled={busy} onChange={e => onSelect(e.target.value)}>
      <MenuItem value="default">Configured chat (existing behavior)</MenuItem>
      {catalog.profiles.map(p => <MenuItem key={p.id} value={p.id} disabled={!p.available}>{p.name}{!p.available ? " · unavailable" : ""}</MenuItem>)}
    </TextField>
    {catalog.profiles.find(p => p.id === selected)?.description && <Typography variant="caption" color="text.secondary">{catalog.profiles.find(p => p.id === selected)?.description}</Typography>}
    <Stack direction="row" gap={1} flexWrap="wrap">{catalog.profiles.map(p => <Chip key={p.id} label={p.name} title={p.unavailable_reason ?? p.description} color={comparison.includes(p.id) ? "primary" : "default"} variant={comparison.includes(p.id) ? "filled" : "outlined"} disabled={busy || !p.available} onClick={() => onComparison(comparison.includes(p.id) ? comparison.filter(id => id !== p.id) : comparison.length < 3 ? [...comparison, p.id] : comparison)} />)}</Stack>
    {catalog.profiles.filter(p => !p.available).map(p => <Typography variant="caption" color="text.secondary" key={p.id}>{p.name}: {p.unavailable_reason}</Typography>)}
    <Typography variant="caption" color="text.secondary">Choose two or three comparison chips. Each mode makes its own retrieval and chat calls using the same question, scope, and conversation history. Profiles change query behavior; they do not rebuild embeddings.</Typography>
    <Button sx={{ alignSelf: "start" }} variant="outlined" disabled={busy || !canCompare || comparison.length < 2} onClick={onCompare}>Compare selected modes</Button>
  </Stack>;
}

export function RagRunDetails({ trace }: { trace: RagTrace }) {
  return <Stack spacing={1}>
    <Typography variant="caption">{trace.profile_id} · {trace.result.stop_reason} · {trace.result.elapsed_seconds.toFixed(2)}s · Searches: {trace.result.retrieval_calls} · Chat calls: {trace.chat_calls} · Reranker calls: {trace.reranker_calls}</Typography>
    {trace.warnings.map(warning => <Alert severity="info" key={warning}>{warning}</Alert>)}
    <Accordion disableGutters><AccordionSummary expandIcon={<ExpandMoreIcon />}>Inspect evidence and steps</AccordionSummary><AccordionDetails><Stack spacing={2}>
      <Typography variant="caption">Corpus check: {trace.corpus_check} · {trace.consistency}. This detects observed local changes; it is not a transactional snapshot.</Typography>
      {trace.result.steps.map((step, i) => <Box key={i}><Typography variant="subtitle2">Search {i + 1}: {step.query}</Typography><Typography variant="body2">Decision: {step.action} · Added {step.added_ids.length} passages · Model: {step.model || "none"}</Typography></Box>)}
      {trace.result.evidence.map(e => <Paper variant="outlined" key={e.id} sx={{ p: 1.5 }}><Typography variant="subtitle2" sx={{ overflowWrap: "anywhere" }}>{e.source_relpath || e.file_id}</Typography><Typography variant="caption">{e.representation} · Characters {e.char_start ?? "?"}–{e.char_end ?? "?"}</Typography><Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{e.text}</Typography></Paper>)}
      {trace.retrieval.filter(r => r.reranker_called).map((r, i) => <Box key={i}><Typography variant="subtitle2">Reranking: {r.query}</Typography><Box component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(r.ranking, null, 2)}</Box></Box>)}
      <Typography variant="caption">{trace.usage_scope}</Typography>
      <Box component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12 }}>{JSON.stringify(trace.chat_usage, null, 2)}</Box>
    </Stack></AccordionDetails></Accordion>
  </Stack>;
}

export function RagComparisonPanel({ value, catalog, onDownload }: { value: RagComparison; catalog: RagProfiles; onDownload: () => void }) {
  return <Stack spacing={2}>
    <Stack direction="row" alignItems="center" justifyContent="space-between"><Typography variant="h6">Mode comparison</Typography><Button onClick={onDownload}>Download comparison JSON</Button></Stack>
    <Typography variant="body2">Question: {value.query} · Chat model: {value.model}</Typography>
    <Stack direction={{ xs: "column", lg: "row" }} spacing={2} alignItems="stretch">{value.runs.map(run => <Paper variant="outlined" key={run.profile_id} sx={{ p: 2, flex: 1, minWidth: 0 }}><Stack spacing={2}>
      <Typography variant="subtitle1">{catalog.profiles.find(p => p.id === run.profile_id)?.name ?? run.profile_id}</Typography>
      {run.error && <Alert severity="error">{run.error}</Alert>}
      {run.response && <><Typography color="text.secondary" variant="caption">{run.response.provider} · {run.response.model} · Retrieval used: {run.response.retrieval_mode}</Typography><Typography sx={{ whiteSpace: "pre-wrap" }}>{run.response.answer}</Typography><Typography variant="caption">{run.response.citations.length} cited passages</Typography>{run.response.experiment && <RagRunDetails trace={run.response.experiment} />}</>}
    </Stack></Paper>)}</Stack>
  </Stack>;
}
