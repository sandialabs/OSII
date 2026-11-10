import { useMemo, useState } from "react";
import { Alert, Box, Button, Chip, Divider, Paper, Stack, Tab, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tabs, Typography } from "@mui/material";
import type { AgentTrace, TraceEvidence, TraceStage } from "../traceTypes";

const json = (value: unknown) => JSON.stringify(value, null, 2);
const codeStyle = { whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12, m: 0, maxHeight: 420, overflowY: "auto" } as const;

function EvidenceTable({ items, onOpen }: { items: TraceEvidence[]; onOpen?: (item: TraceEvidence) => void }) {
  if (!items.length) return <Typography variant="body2" color="text.secondary">No evidence payload recorded here.</Typography>;
  return <TableContainer sx={{ maxHeight: 500 }}><Table size="small" stickyHeader>
    <TableHead><TableRow><TableCell>Evidence</TableCell><TableCell>Rank / score</TableCell><TableCell>Text / exclusion</TableCell></TableRow></TableHead>
    <TableBody>{items.map((item, i) => <TableRow key={`${item.id ?? item.chunk_id}-${i}`}>
      <TableCell sx={{ verticalAlign: "top", maxWidth: 240, overflowWrap: "anywhere" }}>
        <Typography variant="body2">{item.source_relpath ?? item.filename ?? item.file_id ?? item.id}</Typography>
        <Typography variant="caption">{item.representation} {item.char_start != null ? ` · Characters ${item.char_start}–${item.char_end}` : ""}</Typography>
        {item.file_id && onOpen && <Button size="small" onClick={() => onOpen(item)}>Open source</Button>}
        <Box component="details"><Box component="summary" sx={{ cursor: "pointer" }}>Identity and geometry</Box><Box component="pre" sx={codeStyle}>{json({ id: item.id ?? item.chunk_id, file_id: item.file_id, source_origin: item.source_origin })}</Box></Box>
      </TableCell>
      <TableCell sx={{ verticalAlign: "top" }}>{item.rank ?? "—"} / {item.score ?? "—"}</TableCell>
      <TableCell sx={{ verticalAlign: "top", minWidth: 180 }}>
        {item.reason && <Chip size="small" label={item.reason} variant="outlined" />}
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{item.text}</Typography>
        {item.text_truncated && <Typography variant="caption">Preview truncated; original passage has {item.text_characters} characters.</Typography>}
      </TableCell>
    </TableRow>)}</TableBody>
  </Table></TableContainer>;
}

export function AgentTraceViewer({ trace, onOpenEvidence }: { trace: AgentTrace; onOpenEvidence?: (item: TraceEvidence) => void }) {
  const [tab, setTab] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const stage = trace.stages.find(s => s.id === selected) ?? trace.stages.find(s => s.kind === "coarse_fulltext") ?? trace.stages[0];
  const lineage = useMemo(() => trace.stages.flatMap(s => [
    ...s.items.map(item => ({ stage: s, item, selected: true })),
    ...s.excluded.map(item => ({ stage: s, item, selected: false })),
  ]), [trace]);
  const [fileFilter, setFileFilter] = useState("");
  const files = [...new Map(lineage.filter(row => row.item.file_id).map(row => [row.item.file_id!, row.item.source_relpath ?? row.item.file_id!])).entries()];
  const followed = lineage.filter(row => !fileFilter || row.item.file_id === fileFilter);
  const detailed = trace.capture_level === "detailed";
  function depth(value: TraceStage) {
    let current = value, n = 0;
    while (current.parent_id && n < 8) {
      const parent = trace.stages.find(s => s.id === current.parent_id);
      if (!parent) break;
      current = parent; n++;
    }
    return n;
  }
  function download() {
    const url = URL.createObjectURL(new Blob([json(trace)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `osii-agent-trace-${trace.id}.json`; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <Paper variant="outlined" sx={{ p: 2, minWidth: 0 }}><Stack spacing={2}>
    <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap"><Typography variant="h6">Agent trace</Typography><Chip size="small" label={trace.capture_level} /><Chip size="small" label={trace.stop_reason ?? "completed"} /><Button onClick={download}>Download trace JSON</Button></Stack>
    <Typography variant="body2">{trace.profile_id} · Corpus revision {trace.corpus_revision ?? "unknown"} · {trace.elapsed_seconds.toFixed(2)}s · Chat calls: {trace.chat_calls ?? "unknown"}</Typography>
    {trace.warnings?.map(w => <Alert key={w} severity="info">{w}</Alert>)}
    <Typography variant="caption" color="text.secondary">Quality is not measured for this live run. Inspect supporting evidence and compare against labeled questions. {trace.usage_scope}</Typography>
    {!detailed && <Alert severity="info">Administrators can inspect queries, candidates, exclusions, and model usage. This view shows execution counts and status.</Alert>}
    <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable"><Tab label="Execution timeline" /><Tab label="Evidence lineage" disabled={!detailed} /><Tab label="Run JSON" /></Tabs>
    {tab === 0 && <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
      <Stack spacing={0.5} sx={{ minWidth: { md: 290 }, maxWidth: { md: 380 }, maxHeight: 650, overflowY: "auto" }}>
        {trace.stages.map(s => <Button key={s.id} variant={s.id === stage?.id ? "outlined" : "text"} color={s.status === "error" ? "error" : "primary"} onClick={() => setSelected(s.id)} sx={{ justifyContent: "flex-start", textAlign: "left", textTransform: "none", color: s.status === "error" ? "error.main" : "text.primary", ml: depth(s), flexShrink: 0 }}>
          <Stack><Typography variant="body2">{s.id}. {s.label}</Typography><Typography variant="caption">{s.status} · +{s.started_seconds.toFixed(2)}s · {s.duration_seconds.toFixed(3)}s · {String(s.inputs.input_count ?? "—")} → {String(s.outputs.output_count ?? "—")}</Typography></Stack>
        </Button>)}
      </Stack>
      {stage && <Stack spacing={1.5} sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="subtitle1">{stage.label}</Typography>
        <Typography variant="caption">{stage.kind} · {stage.status} · Parent: {stage.parent_id ?? "run root"}</Typography>
        <Typography variant="subtitle2">Inputs</Typography><Box component="pre" sx={codeStyle}>{json(stage.inputs)}</Box>
        <Typography variant="subtitle2">Outputs and limits</Typography><Box component="pre" sx={codeStyle}>{json(stage.outputs)}</Box>
        {detailed && <><Divider /><Typography variant="subtitle2">Returned / retained evidence</Typography><EvidenceTable items={stage.items} onOpen={onOpenEvidence} />
          {stage.excluded.length > 0 && <><Typography variant="subtitle2">Excluded evidence</Typography><EvidenceTable items={stage.excluded} onOpen={onOpenEvidence} /></>}</>}
      </Stack>}
    </Stack>}
    {tab === 1 && <Stack spacing={1}>
      <Box component="label">Follow a source document: <Box component="select" value={fileFilter} onChange={event => setFileFilter(event.target.value)} sx={{ maxWidth: "100%", p: 1 }}><option value="">All evidence</option>{files.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</Box></Box>
      <Typography variant="caption">Showing {Math.min(followed.length, 200)} of {followed.length} captured transitions. Select a source to narrow the view.</Typography>
      {followed.slice(0, 200).map((row, i) => <Paper variant="outlined" sx={{ p: 1.5 }} key={i}><Stack spacing={0.5}>
        <Button sx={{ alignSelf: "start" }} onClick={() => { setSelected(row.stage.id); setTab(0); }}>{row.stage.id}. {row.stage.label}</Button>
        <Typography variant="body2">{row.item.source_relpath ?? row.item.file_id} · {row.item.id ?? row.item.chunk_id} · {row.selected ? "retained / returned" : row.item.reason}</Typography>
      </Stack></Paper>)}
    </Stack>}
    {tab === 2 && <Box component="pre" sx={{ ...codeStyle, maxHeight: 600, overflowY: "auto" }}>{json(trace)}</Box>}
    <Typography variant="caption" color="text.secondary">Trace {trace.id} · {trace.persistence}</Typography>
  </Stack></Paper>;
}
