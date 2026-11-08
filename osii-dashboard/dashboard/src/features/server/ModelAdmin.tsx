import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, FormControlLabel, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, Typography } from "@mui/material";
import { EndpointFields } from "../models/components/EndpointFields";
import { ModelPicker, type ModelOption } from "../models/components/ModelPicker";
import { api } from "./api";

type Kind = "chat" | "embedding" | "rerank";
type Endpoint = { base_url: string; model: string; model_name?: string; configured: boolean; credential_present: boolean; managed_by?: string };
type Configuration = { endpoints: Record<Kind, Endpoint> };
const labels: Record<Kind, string> = { chat: "Language model", embedding: "Embedding model", rerank: "Reranker" };
const purposes: Record<Kind, string> = { chat: "Chat and grounded answers", embedding: "Semantic and hybrid search", rerank: "Optional ranking in RAG strategies" };
const kinds: Kind[] = ["chat", "embedding", "rerank"];

function ConnectionDialog({ kind, endpoint, close, saved }: { kind: Kind; endpoint: Endpoint; close: () => void; saved: () => Promise<void> }) {
  const [url, setUrl] = useState(endpoint.base_url);
  const [key, setKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [model, setModel] = useState(endpoint.model || "");
  const [options, setOptions] = useState<ModelOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [finding, setFinding] = useState(false);
  const [queried, setQueried] = useState(false);
  const [error, setError] = useState("");
  const version = useRef(0);
  const findModels = async () => {
    const request = version.current;
    setFinding(true); setError("");
    try {
      const result = await api<{ models: ModelOption[] }>(`/api/admin/models/endpoints/${kind}/discover`, "POST", {
        base_url: url, clear_api_key: clearKey, ...(key ? { api_key: key } : {}),
      });
      if (request === version.current) { setOptions(result.models); setQueried(true); }
    } catch (e) { if (request === version.current) setError((e as Error).message); }
    finally { setFinding(false); }
  };
  const save = async () => {
    setBusy(true); setError("");
    try {
      await api(`/api/admin/models/endpoints/${kind}`, "PUT", { base_url: url, model, clear_api_key: clearKey,
        model_name: options.find(option => option.id === model)?.name || (model === endpoint.model ? endpoint.model_name : model),
        ...(key ? { api_key: key } : {}),
      });
      setKey(""); await saved(); close();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const reset = async () => {
    setBusy(true); setError("");
    try { await api(`/api/admin/models/endpoints/${kind}`, "DELETE"); setKey(""); await saved(); close(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const credentialPresent = url.trim().replace(/\/$/, "") === endpoint.base_url && endpoint.credential_present;
  return <Dialog open onClose={busy ? undefined : close} fullWidth maxWidth="md"><DialogTitle>{endpoint.model ? "Change" : "Add"} {labels[kind].toLowerCase()}</DialogTitle>
    <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
      <Typography color="text.secondary">Enter the service address and key, then find its available models. Choose a model by name. This lookup does not save settings or generate content.</Typography>
      <EndpointFields baseUrl={url} onBaseUrl={value => { version.current += 1; setUrl(value); setOptions([]); setQueried(false); setModel(""); }}
        apiKey={key} onApiKey={value => { version.current += 1; setClearKey(false); setKey(value); setOptions([]); setQueried(false); }} credentialPresent={credentialPresent}
        onDiscover={() => void findModels()} discovering={finding} required urlHelp="Use the service's API base address, including /v1 or /v2 when required." />
      {credentialPresent && <FormControlLabel control={<Checkbox checked={clearKey} onChange={e => { setClearKey(e.target.checked); setKey(""); version.current += 1; setOptions([]); setQueried(false); }} />} label="Remove the saved API key (this service needs no key)" />}
      {error && <Alert severity="error">{error}</Alert>}
      {queried && <Alert severity="info">{options.length} available {kind === "chat" ? "language" : kind === "embedding" ? "embedding" : "reranking"} models found. Choose one below; these have not been added to OSII yet.</Alert>}
      <ModelPicker label={labels[kind]} value={model} options={options} onChange={setModel}
        helperText={queried ? "Search the available models and select one to use." : "Use Find available models above, or enter a published model name manually."} />
      {kind === "embedding" && <Typography variant="body2" color="text.secondary">Changing this model may require reprocessing documents. Keyword search continues to work without it.</Typography>}
      <Typography variant="caption" color="text.secondary">One active connection is supported for each purpose. Saving replaces the current {labels[kind].toLowerCase()} connection.</Typography>
    </Stack></DialogContent>
    <DialogActions>{endpoint.managed_by === "administrator" && <Button color="secondary" disabled={busy} onClick={() => void reset()}>Use deployment default</Button>}<Button color="secondary" onClick={close} disabled={busy}>Cancel</Button><Button color="secondary" variant="contained" onClick={() => void save()} disabled={busy || !url.trim() || !model.trim()}>{busy ? "Saving…" : "Save connection"}</Button></DialogActions>
  </Dialog>;
}

export function ModelAdmin() {
  const [config, setConfig] = useState<Configuration | null>(null);
  const [editing, setEditing] = useState<Kind | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<Kind | null>(null);
  const refresh = async () => setConfig(await api<Configuration>("/api/admin/models"));
  useEffect(() => { void refresh().catch(e => setError(e.message)); }, []);
  const test = async (kind: Kind) => {
    setBusy(kind); setError(""); setNotice("");
    try {
      const checks = await api<Record<string, { ok?: boolean; detail?: string }>>(`/api/admin/models/test?only=${kind}`, "POST", {});
      if (!checks[kind]?.ok) throw new Error(checks[kind]?.detail || "No usable model is selected.");
      setNotice(`${labels[kind]} responded successfully to a small sample request.`);
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const disable = async (kind: Kind) => {
    setBusy(kind); setError("");
    try { await api(`/api/admin/models/endpoints/${kind}`, "PUT", { base_url: kind === "rerank" ? "" : config?.endpoints[kind].base_url || "", model: "", clear_api_key: kind === "rerank" }); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const configured = config ? kinds.filter(kind => config.endpoints[kind]?.configured && config.endpoints[kind]?.model) : [];
  return <Stack spacing={3}>
    <Box><Typography variant="h5">Model connections</Typography><Typography color="text.secondary">Choose the services OSII uses. Models are optional for browsing and keyword search.</Typography></Box>
    {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}{notice && <Alert severity="success" onClose={() => setNotice("")}>{notice}</Alert>}
    <Paper sx={{ p: 3 }}><Stack spacing={2}><Typography variant="h6">Configured models</Typography>
      {!config ? <Typography>Loading connections…</Typography> : !configured.length ? <Typography color="text.secondary">No models have been selected. You can use keyword search now, or add a connection below.</Typography> : configured.map(kind => {
        const endpoint = config.endpoints[kind];
        return <Paper key={kind} variant="outlined" sx={{ p: 2 }}><Stack spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center"><Typography fontWeight={700}>{labels[kind]}</Typography><Chip size="small" label="Configured" /></Stack>
          <Typography>{endpoint.model_name || endpoint.model}</Typography><Typography variant="caption" color="text.secondary">{purposes[kind]} · {endpoint.base_url}</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap"><Button color="secondary" onClick={() => setEditing(kind)}>Change connection</Button><Button color="secondary" disabled={busy !== null} onClick={() => void test(kind)}>Test with sample text</Button><Button color="secondary" disabled={busy !== null} onClick={() => void disable(kind)}>Remove selection</Button></Stack>
        </Stack></Paper>;
      })}
      {!!configured.length && <Typography variant="caption" color="text.secondary">Sample tests invoke only the selected connection and may use provider credit. Saved keys are never displayed.</Typography>}
    </Stack></Paper>
    <Paper variant="outlined" sx={{ p: 3 }}><Stack spacing={2}><Typography variant="h6">Add a model connection</Typography>
      <Typography color="text.secondary">Find the models offered by your endpoint, then choose one. Available models become configured only when you save a selection.</Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>{kinds.filter(kind => !configured.includes(kind)).map(kind => <Button color="secondary" key={kind} variant="outlined" disabled={!config} onClick={() => setEditing(kind)}>Add {labels[kind].toLowerCase()}</Button>)}
      {configured.length === kinds.length && <Typography color="text.secondary">Each purpose has a connection. Use Change connection above to select a different service or model.</Typography>}</Stack>
    </Stack></Paper>
    {editing && config && <ConnectionDialog key={editing} kind={editing} endpoint={config.endpoints[editing]} close={() => setEditing(null)} saved={async () => { await refresh(); setNotice(`${labels[editing]} connection saved.`); }} />}
  </Stack>;
}
