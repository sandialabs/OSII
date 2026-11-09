import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Button, Chip, CircularProgress, MenuItem, Stack, TextField, Typography } from "@mui/material";
import PlayArrowOutlined from "@mui/icons-material/PlayArrowOutlined";
import ExpandMoreOutlined from "@mui/icons-material/ExpandMoreOutlined";
import { Link } from "react-router-dom";
import { getToolCatalog } from "../../../api/tools";
import { controlProcessingRun, getProcessingRun } from "../../../api/queue";
import type { ScopeDescribeRequest } from "../../../api/types";
import { useEnrichmentJob } from "../../../hooks/useEnrichmentJob";
import { ProcessorConfigInput } from "../../queue/components/ProcessorConfigInput";

const activeStatuses = ["pending", "queued", "running", "pausing", "cancelling"];

/** One action surface for every registered scope tool, including new methods. */
export function ToolActionPanel({ scope, action, title }: { scope: ScopeDescribeRequest; action?: string; title?: string }) {
  const client = useQueryClient();
  const catalog = useQuery({ queryKey: ["tool-catalog"], queryFn: getToolCatalog, staleTime: 30_000 });
  const methods = useMemo(() => (catalog.data?.methods ?? []).filter(method => method.execution === "scope" && method.scopes.includes(scope.scope_type) && (!action || method.action === action)), [catalog.data, scope.scope_type, action]);
  const [selected, setSelected] = useState("");
  const [model, setModel] = useState("__configured__");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const method = methods.find(item => item.id === selected) ?? methods[0];
  const job = useEnrichmentJob();
  const key = `osii:tool-run:${catalog.data?.library_id}:${JSON.stringify(scope)}:${action ?? "all"}`;
  const [runId, setRunId] = useState("");
  useEffect(() => { setRunId(localStorage.getItem(key) ?? ""); }, [key]);
  const run = useQuery({ queryKey: ["processing-run", runId], queryFn: () => getProcessingRun(runId), enabled: Boolean(runId),
    refetchInterval: query => query.state.error ? false : activeStatuses.includes(query.state.data?.status ?? "queued") ? 1200 : false });
  useEffect(() => {
    if (run.data && ["done", "error", "cancelled"].includes(run.data.status)) {
      void client.invalidateQueries({ queryKey: ["enrichments"] });
      void client.invalidateQueries({ queryKey: ["product-history"] });
    }
  }, [run.data?.status, client]);
  const control = useMutation({ mutationFn: (command: "pause" | "resume" | "cancel" | "retry") => controlProcessingRun(runId, command), onSuccess: () => { void run.refetch(); } });
  const active = job.isPending || Boolean(runId && !run.data && !run.isError) || activeStatuses.includes(run.data?.status ?? "");
  const chatModels = catalog.data?.models.filter(item => item.capabilities.includes("chat")) ?? [];
  const configuredModel = chatModels.find(item => item.id === method?.bindings.chat);
  const libraryModel = chatModels.find(item => item.id === catalog.data?.defaults.chat) ?? chatModels[0];
  const error = job.error ?? control.error ?? run.error;
  const generate = async () => {
    if (!method) return;
    const properties = method.config_schema.properties ?? {};
    const result = await job.mutateAsync({ enricher_name: method.id, scope,
      ...(model !== "__configured__" ? { model_bindings: { chat: model === "__library__" ? "" : model } } : {}),
      enricher_config: { ...(properties.title && title ? { title: `${title} Wiki` } : {}), ...config } });
    setRunId(result.run_id);
    localStorage.setItem(key, result.run_id);
  };
  if (catalog.isPending) return <CircularProgress size={22} />;
  if (catalog.isError) return <Alert severity="error">Tools could not be loaded. <Button onClick={() => void catalog.refetch()}>Retry</Button></Alert>;
  if (!method) return <Alert severity="info">No compatible method is connected. <Link to="/admin/processors">Open Setup</Link></Alert>;
  return <Stack spacing={1.5}>
    <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
      <TextField select size="small" label="Method" value={method.id} onChange={event => { setSelected(event.target.value); setConfig({}); setModel("__configured__"); }} sx={{ minWidth: 250 }}>
        {methods.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      {method.model_requirements.chat ? <TextField select size="small" label="Writing model" value={model} onChange={event => setModel(event.target.value)} sx={{ minWidth: 300 }}>
        <MenuItem value="__configured__">{configuredModel && configuredModel.id !== libraryModel?.id ? "Configured" : "Library default"} — {method.configuration_error ? "Choose a model" : configuredModel?.label ?? libraryModel?.label ?? "Choose in Setup"}</MenuItem>
        {configuredModel?.id !== libraryModel?.id ? <MenuItem value="__library__">Library default — {libraryModel?.label ?? "Choose in Setup"}</MenuItem> : null}
        {chatModels.map(item => <MenuItem value={item.id} key={item.id}>{item.label}</MenuItem>)}
      </TextField> : null}
      <Button variant="contained" startIcon={<PlayArrowOutlined />} disabled={active || Boolean(method.configuration_error && model === "__configured__") || Boolean(method.model_requirements.chat === "required" && !chatModels.length)} onClick={() => { void generate().catch(() => {}); }}>
        {active ? "Working…" : action === "wiki.write" ? "Generate wiki" : "Run"}
      </Button>
    </Stack>
    {method.configuration_error && model === "__configured__" ? <Alert severity="warning">{method.configuration_error} Choose a model above or <Link to="/admin/processors">open Setup</Link>.</Alert> : null}
    {Object.keys(method.config_schema.properties ?? {}).filter(name => name !== "title").length ? <Accordion disableGutters elevation={0}>
      <AccordionSummary expandIcon={<ExpandMoreOutlined />}><Typography variant="body2">Options</Typography></AccordionSummary>
      <AccordionDetails><Stack spacing={2}>{Object.entries(method.config_schema.properties ?? {}).filter(([name]) => name !== "title").map(([name, property]) => <ProcessorConfigInput key={name} name={name} property={property} value={config[name] ?? property.default} onChange={value => setConfig(old => ({ ...old, [name]: value }))} />)}</Stack></AccordionDetails>
    </Accordion> : null}
    <Typography variant="caption" color="text.secondary">Up to {method.limits.documents.toLocaleString()} documents · {method.limits.characters.toLocaleString()} text characters. Source coverage is saved with the result.</Typography>
    {runId ? <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Chip size="small" icon={active ? <CircularProgress size={12} /> : undefined} label={run.data?.status === "done" ? "Saved" : run.data?.status ?? "Queued"} color={run.data?.status === "error" ? "error" : run.data?.status === "done" ? "success" : "default"} />
      <Button component={Link} to="/intake?tab=activity" size="small">Activity ↗</Button>
      {run.data?.status === "error" ? <Button size="small" disabled={control.isPending} onClick={() => control.mutate("retry")}>Retry</Button> : null}
      {run.data?.status === "paused" ? <Button size="small" onClick={() => control.mutate("resume")}>Resume</Button> : null}
      {active ? <Button size="small" disabled={control.isPending} onClick={() => control.mutate("cancel")}>Cancel</Button> : null}
    </Stack> : null}
    {active ? <Typography variant="caption" color="text.secondary">You can leave this page. Your last saved result stays available.</Typography> : null}
    {run.data?.status === "error" ? <Alert severity="error">{run.data.error || "The tool failed. Its inputs are saved for retry."}</Alert> : null}
    {run.isError ? <Button size="small" onClick={() => { setRunId(""); localStorage.removeItem(key); }}>Dismiss unavailable run</Button> : null}
    {error ? <Alert severity="error">{error instanceof Error ? error.message : "The request failed."}</Alert> : null}
  </Stack>;
}
