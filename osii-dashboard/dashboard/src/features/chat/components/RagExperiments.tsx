import { Alert, Button, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import type { RagComparison, RagProfiles } from "../types";
import { AgentTraceViewer } from "./AgentTraceViewer";
import type { TraceEvidence } from "../traceTypes";

export function RagProfileControls({ catalog, selected, onSelect, comparison, onComparison, busy, onCompare, canCompare }: {
  catalog: RagProfiles; selected: string; onSelect: (id: string) => void; comparison: string[];
  onComparison: (ids: string[]) => void; busy: boolean; onCompare: () => void; canCompare: boolean;
}) {
  return <Stack spacing={1.5}>
    <Typography variant="subtitle2">Advanced RAG · Chat model: {catalog.chat_model}</Typography>
    <TextField select label="RAG strategy" value={selected} disabled={busy} onChange={e => onSelect(e.target.value)}>
      <MenuItem value="default">Configured chat (single pass)</MenuItem>
      {catalog.profiles.map(p => <MenuItem key={p.id} value={p.id} disabled={!p.available}>{p.name}{!p.available ? " · unavailable" : ""}</MenuItem>)}
    </TextField>
    <Typography variant="caption">{catalog.profiles.find(p => p.id === selected)?.description}</Typography>
    <Stack direction="row" gap={1} flexWrap="wrap">{catalog.profiles.map(p => <Chip key={p.id} label={p.name} title={p.unavailable_reason ?? p.description} color={comparison.includes(p.id) ? "primary" : "default"} variant={comparison.includes(p.id) ? "filled" : "outlined"} disabled={busy || !p.available} onClick={() => onComparison(comparison.includes(p.id) ? comparison.filter(id => id !== p.id) : comparison.length < 3 ? [...comparison, p.id] : comparison)} />)}</Stack>
    {catalog.profiles.filter(p => !p.available).map(p => <Typography key={p.id} variant="caption" color="text.secondary">{p.name}: {p.unavailable_reason}</Typography>)}
    <Typography variant="caption" color="text.secondary">Choose two or three comparison chips. Each strategy uses the same question, scope, history, and corpus snapshot, and makes its own model calls. Iterative strategies can use up to three chat calls. Normal provider charges apply. Strategy selection does not process or re-embed documents.</Typography>
    <Button sx={{ alignSelf: "start" }} disabled={busy || !canCompare || comparison.length < 2} variant="outlined" onClick={onCompare}>Compare selected strategies</Button>
  </Stack>;
}

export function RagComparisonPanel({ value, catalog, onOpenEvidence }: { value: RagComparison; catalog: RagProfiles; onOpenEvidence: (item: TraceEvidence) => void }) {
  return <Stack spacing={2}>
    <Typography variant="h6">Strategy comparison</Typography>
    <Typography variant="body2">{value.query} · Corpus revision {value.corpus_revision} · {value.model}</Typography>
    {value.runs.map(run => <Paper variant="outlined" key={run.profile_id} sx={{ p: 2 }}><Stack spacing={2}>
      <Typography variant="h6">{catalog.profiles.find(p => p.id === run.profile_id)?.name ?? run.profile_id}</Typography>
      {run.response.error && <Alert severity="error">{run.response.error}</Alert>}
      <Typography sx={{ whiteSpace: "pre-wrap" }}>{run.response.answer}</Typography>
      <Typography variant="caption">{run.response.citations.length} cited passages · Retrieval used: {run.response.retrieval_mode}</Typography>
      {run.response.agent_trace && <AgentTraceViewer trace={run.response.agent_trace} onOpenEvidence={onOpenEvidence} />}
    </Stack></Paper>)}
  </Stack>;
}
