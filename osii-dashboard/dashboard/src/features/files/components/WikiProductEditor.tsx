import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Chip, MenuItem, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import EditOutlined from "@mui/icons-material/EditOutlined";
import SaveOutlined from "@mui/icons-material/SaveOutlined";
import { getProductHistory, saveProduct, type ProductHistory } from "../../../api/tools";
import type { ScopeDescribeRequest } from "../../../api/types";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";

type Draft = { text: string; base: string };
function readDraft(key: string): Draft | null {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "null");
    return typeof value?.text === "string" && typeof value?.base === "string" ? value : null;
  } catch { return null; }
}

function Editor({ scope, filename, history, draftKey }: { scope: ScopeDescribeRequest; filename: string; history: ProductHistory; draftKey: string }) {
  const client = useQueryClient();
  const [tab, setTab] = useState("read");
  const [draft, setDraft] = useState<Draft | null>(() => readDraft(draftKey));
  const [compare, setCompare] = useState(history.revisions[history.revisions.length - 1]?.id ?? "");
  const [storageError, setStorageError] = useState(false);
  const current = history.revisions.find(item => item.id === history.current);
  const candidate = history.revisions.find(item => item.id === compare);
  const hasCandidates = history.revisions.some(item => item.id !== history.current && item.origin === "generated" && item.parent === history.current);
  const changed = draft && draft.base !== history.current;
  const save = useMutation({
    mutationFn: (change: { markdown: string; base: string } | { revision: string }) => saveProduct(scope, filename, "base" in change ? change.base : history.current, "markdown" in change ? { markdown: change.markdown } : change),
    onSuccess: async (_, change) => {
      if ("markdown" in change) { setDraft(null); localStorage.removeItem(draftKey); setTab("read"); }
      await Promise.all([client.invalidateQueries({ queryKey: ["product-history", scope, filename] }), client.invalidateQueries({ queryKey: ["enrichments"] })]);
    },
  });
  useEffect(() => {
    if (!draft) return;
    try { localStorage.setItem(draftKey, JSON.stringify(draft)); setStorageError(false); }
    catch { setStorageError(true); }
  }, [draft, draftKey]);
  const startEdit = () => { if (!draft) setDraft({ text: history.data.markdown, base: history.current }); setTab("edit"); };
  return <Stack spacing={1.5}>
    <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
      <Tabs value={tab} onChange={(_, value: string) => value === "edit" ? startEdit() : (value === "history" && setCompare(history.revisions[history.revisions.length - 1]?.id ?? ""), setTab(value))} aria-label="Wiki views">
        <Tab value="read" label="Read" /><Tab value="edit" label="Edit" disabled={history.permissions?.edit === false} /><Tab value="history" label={`History (${history.revisions.length})`} />
      </Tabs>
      {tab !== "edit" && history.permissions?.edit !== false ? <Button size="small" startIcon={<EditOutlined />} onClick={startEdit}>{draft ? "Resume draft" : "Edit"}</Button> : null}
    </Stack>
    {history.input_state === "stale" ? <Alert severity="warning">Source text or scope membership changed since this version was generated.</Alert> : null}
    {hasCandidates ? <Alert severity="info" action={<Button size="small" onClick={() => { setCompare(history.revisions[history.revisions.length - 1]?.id ?? ""); setTab("history"); }}>Review</Button>}>A generated version is ready for review.</Alert> : null}
    {current?.grounding_needs_review ? <Typography variant="caption" color="text.secondary">Edited text · citation grounding needs review.</Typography> : null}
    {tab === "read" ? <EnrichmentArtifactView data={history.data} showTitle={false} /> : null}
    {tab === "edit" && draft ? <>
      {changed ? <Alert severity="warning">The saved wiki changed while this draft was open. Compare the latest text in History, then explicitly rebase your draft.</Alert> : null}
      <TextField multiline minRows={16} maxRows={36} fullWidth label="Wiki Markdown" value={draft.text} onChange={event => setDraft({ ...draft, text: event.target.value })} inputProps={{ style: { fontFamily: "monospace", fontSize: 14 } }} />
      <Stack direction="row" spacing={1}>
        <Button startIcon={<SaveOutlined />} variant="contained" disabled={save.isPending || Boolean(changed)} onClick={() => save.mutate({ markdown: draft.text, base: draft.base })}>Save</Button>
        {changed ? <Button onClick={() => setDraft({ ...draft, base: history.current })}>Use latest as base</Button> : null}
        <Button onClick={() => { setTab("read"); }}>Keep draft</Button>
        <Button color="error" onClick={() => { setDraft(null); localStorage.removeItem(draftKey); setTab("read"); }}>Discard draft</Button>
      </Stack>
      <Typography variant="caption" color="text.secondary">{storageError ? "Browser storage is full. Keep this page open until you save." : "Draft saved on this device. Save creates a new revision."}</Typography>
    </> : null}
    {tab === "history" ? <>
      <TextField select size="small" label="Compare revision" value={compare} onChange={event => setCompare(event.target.value)}>
        {[...history.revisions].reverse().map(item => <MenuItem key={item.id} value={item.id}>{item.origin === "human" ? "Edited" : item.origin === "imported" ? "Original" : "Generated"} · {item.created_at ? new Date(item.created_at).toLocaleString() : "Imported"}{item.id === history.current ? " · Current" : ""}</MenuItem>)}
      </TextField>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} divider={<span aria-hidden="true">│</span>}>
        <Stack flex={1} minWidth={0}><Typography fontWeight={700}>Current</Typography><EnrichmentArtifactView data={history.data} showTitle={false} /></Stack>
        <Stack flex={1} minWidth={0}><Typography fontWeight={700}>Selected revision</Typography>{candidate ? <EnrichmentArtifactView data={candidate.data} showTitle={false} /> : null}</Stack>
      </Stack>
      {candidate && candidate.id !== history.current && history.permissions?.edit !== false ? <Button variant="outlined" disabled={save.isPending} onClick={() => save.mutate({ revision: candidate.id })} sx={{ alignSelf: "flex-start" }}>Use this revision</Button> : null}
      {candidate?.provenance.inputs ? <Stack direction="row" spacing={1}>
        <Chip size="small" label={`${candidate.provenance.inputs.length} source documents`} />
        {candidate.provenance.inputs.some(item => item.truncated) ? <Chip size="small" label="Bounded excerpts" /> : null}
      </Stack> : null}
    </> : null}
    {save.isError ? <Alert severity="error">{save.error instanceof Error ? save.error.message : "Could not save this wiki. Your draft is preserved."}</Alert> : null}
  </Stack>;
}

export function WikiProductEditor({ scope, filename }: { scope: ScopeDescribeRequest; filename: string }) {
  const history = useQuery({ queryKey: ["product-history", scope, filename], queryFn: () => getProductHistory(scope, filename) });
  if (history.isError) return <Alert severity="error">This wiki could not be loaded. <Button onClick={() => void history.refetch()}>Retry</Button></Alert>;
  if (!history.data?.data) return <Typography color="text.secondary">Loading wiki…</Typography>;
  const key = `osii:wiki-draft:${history.data.library_id}:${JSON.stringify(scope)}:${filename}`;
  return <Editor key={key} scope={scope} filename={filename} history={history.data} draftKey={key} />;
}
