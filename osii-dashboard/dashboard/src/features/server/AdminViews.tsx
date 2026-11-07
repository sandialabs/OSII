import { useEffect, useState } from "react";
import { Alert, Autocomplete, Box, Button, Checkbox, Chip, FormControlLabel, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { api, type Model, type User } from "./api";

import { EndpointFields } from "../models/components/EndpointFields";

type Endpoint = { base_url: string; model: string; configured: boolean; credential_present: boolean; managed_by?: string };

function EndpointEditor({ kind, endpoint, saved }: { kind: string; endpoint: Endpoint; saved: () => Promise<void> }) {
  const [url, setUrl] = useState(endpoint.base_url);
  const [model, setModel] = useState(endpoint.model || "");
  const [key, setKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (reset = false) => {
    setBusy(true); setError("");
    try {
      await api(`/api/admin/models/endpoints/${kind}`, reset ? "DELETE" : "PUT",
        reset ? undefined : { base_url: url, model, ...(key ? { api_key: key } : {}), clear_api_key: clearKey });
      setKey(""); setClearKey(false); await saved();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
    <Typography variant="subtitle1" sx={{ textTransform: "capitalize" }}>{kind} endpoint</Typography>
    <Chip size="small" sx={{ alignSelf: "start" }} label={`${endpoint.managed_by || "deployment"} · ${endpoint.credential_present ? "key configured" : "no key"}`} />
    <EndpointFields baseUrl={url} onBaseUrl={setUrl} apiKey={key} onApiKey={setKey} credentialPresent={endpoint.credential_present} />
    {kind === "rerank" && <TextField label="Reranker model ID" value={model} onChange={e => setModel(e.target.value)} helperText="Optional Core RAG adapter using a Cohere-compatible /rerank API." />}
    <FormControlLabel control={<Checkbox checked={clearKey} onChange={e => setClearKey(e.target.checked)} />} label="Remove saved key (endpoint needs no authentication)" />
    {error && <Alert severity="error">{error}</Alert>}
    <Stack direction="row" spacing={1}><Button disabled={busy} variant="outlined" onClick={() => void save()}>Save {kind} endpoint</Button><Button disabled={busy} onClick={() => void save(true)}>Use deployment default</Button></Stack>
  </Stack></Paper>;
}

export function ModelAdmin() {
  const [config, setConfig] = useState({ chat_model: "", embedding_model: "", base_url: "", credential_present: false, endpoints: {} as Record<string, Endpoint> });
  const [models, setModels] = useState<Model[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = async () => setConfig(await api<typeof config>("/api/admin/models"));
  useEffect(() => { void refresh().catch(e => setError(e.message)); }, []);
  const action = async (kind: "discover" | "save" | "test") => {
    setBusy(true); setError(""); setNotice("");
    try {
      if (kind === "discover") { const result = await api<{ models: Model[]; warnings?: Record<string, string> }>("/api/admin/models/catalog"); setModels(result.models); setNotice(`Found ${result.models.length} models. Catalog discovery does not test generation or billing access. ${Object.entries(result.warnings || {}).map(([kind, message]) => `${kind}: ${message}`).join(" · ")}`); }
      else if (kind === "save") { await api("/api/admin/models", "PUT", { chat_model: config.chat_model, embedding_model: config.embedding_model }); setNotice("Model selections saved. Changing embeddings requires reprocessing the library."); }
      else { const result = await api<Record<string, { configured: boolean; ok?: boolean; detail?: string }>>("/api/admin/models/test", "POST", {}); setNotice(Object.entries(result).map(([name, check]) => `${name}: ${!check.configured ? "not selected" : check.ok ? "invocation passed" : check.detail}`).join(" · ")); }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <Paper sx={{ p: 3 }}><Stack spacing={2}><Typography variant="h6">Model endpoints</Typography>
    <Typography variant="body2" color="text.secondary">Endpoint changes apply to API and worker without restarting. Keys are write-only and stored by Core in the server database. Changing an embedding endpoint or model may require reprocessing. Keyword search needs no model service. Reranking remains an opt-in Core RAG step.</Typography>
    {Object.entries(config.endpoints).map(([kind, endpoint]) => <EndpointEditor key={`${kind}:${endpoint.base_url}:${endpoint.model}:${endpoint.credential_present}:${endpoint.managed_by}`} kind={kind} endpoint={endpoint} saved={async () => { await refresh(); setNotice(`${kind} endpoint saved.`); }} />)}
    {error && <Alert severity="error">{error}</Alert>}{notice && <Alert severity="info">{notice}</Alert>}
    {(["chat", "embedding"] as const).map(kind => <Autocomplete key={kind} freeSolo options={models.filter(m => !m.capabilities.length || m.capabilities.includes(kind)).map(m => m.id)} value={config[`${kind}_model`]} onChange={(_, value) => setConfig({ ...config, [`${kind}_model`]: value ?? "" })} onInputChange={(_, value, reason) => { if (reason === "input") setConfig(current => ({ ...current, [`${kind}_model`]: value })); }} getOptionLabel={id => { const model = models.find(m => m.id === id); return model ? `${model.name} — ${id}` : id; }} renderInput={params => <TextField {...params} label={kind === "chat" ? "Language model ID" : "Embedding model ID (optional)"} helperText="Choose a discovered model or enter its exact API ID." />} />)}
    <Stack direction="row" spacing={1}><Button disabled={busy} onClick={() => void action("discover")}>Discover models</Button><Button variant="contained" disabled={busy} onClick={() => void action("save")}>Save selection</Button><Button disabled={busy} onClick={() => void action("test")}>Test selected models</Button></Stack>
  </Stack></Paper>;
}

export function UserAdmin() {
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<User["role"]>("reader");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const refresh = () => api<{ users: User[] }>("/api/admin/users").then(r => setUsers(r.users));
  useEffect(() => { void refresh().catch(e => setError(e.message)); }, []);
  const run = async (path: string, method: string, body?: unknown) => {
    setNotice(""); setError("");
    try { const r = await api<{ temporary_password?: string }>(path, method, body); if (r.temporary_password) setNotice(`Temporary password (shown once): ${r.temporary_password}`); await refresh(); } catch (e) { setError((e as Error).message); }
  };
  return <Paper sx={{ p: 3 }}><Stack spacing={2}><Typography variant="h6">User accounts</Typography>{error && <Alert severity="error">{error}</Alert>}{notice && <Alert severity="info" onClose={() => setNotice("")}>{notice}</Alert>}
    <Stack direction="row" spacing={1}><TextField label="New username" value={username} onChange={e => setUsername(e.target.value)} /><TextField select label="Role" value={role} onChange={e => setRole(e.target.value as User["role"])}>{["reader", "curator", "admin"].map(r => <MenuItem key={r} value={r}>{r}</MenuItem>)}</TextField><Button onClick={() => void run("/api/admin/users", "POST", { username, role })}>Create account</Button></Stack>
    {users.map(user => <Stack key={user.id} direction="row" spacing={2} alignItems="center"><Typography sx={{ flex: 1 }}>{user.username} · {user.role} · {user.active ? "active" : "disabled"}</Typography><TextField select size="small" label="Role" value={user.role} onChange={e => void run(`/api/admin/users/${user.id}`, "PATCH", { role: e.target.value })}>{["reader", "curator", "admin"].map(r => <MenuItem key={r} value={r}>{r}</MenuItem>)}</TextField><Button onClick={() => void run(`/api/admin/users/${user.id}`, "PATCH", { active: !user.active })}>{user.active ? "Disable" : "Enable"}</Button><Button onClick={() => void run(`/api/admin/users/${user.id}/reset-password`, "POST", {})}>Reset password</Button></Stack>)}
  </Stack></Paper>;
}

export function Intake() {
  const [runs, setRuns] = useState<{ id: string; status: string; logs: string[]; payload: { source_directory?: string; force?: boolean }; created_at: string }[]>([]);
  const [error, setError] = useState("");
  const [source, setSource] = useState(".");
  const refresh = () => api<{ source_directory: string; runs: typeof runs }>("/api/runs").then(r => { setRuns(r.runs); setSource(r.source_directory); });
  useEffect(() => { void refresh().catch(e => setError(e.message)); const t = window.setInterval(() => { void refresh().catch(e => setError(e.message)); }, 5000); return () => window.clearInterval(t); }, []);
  return <Paper sx={{ p: 3 }}><Stack spacing={2}><Typography variant="h6">Shared dataset processing</Typography><Typography>Selected source folder: {source}. Originals remain unchanged. An administrator can change this under Source & status.</Typography>{error && <Alert severity="error">{error}</Alert>}<Button variant="contained" onClick={() => void api("/api/admin/intake", "POST", {}).then(refresh).catch(e => setError(e.message))}>Process shared dataset</Button><Button onClick={() => void api("/api/admin/intake", "POST", { force: true }).then(refresh).catch(e => setError(e.message))}>Reprocess all documents</Button><Typography variant="body2" color="text.secondary">Reprocessing repeats extraction and any configured embedding calls.</Typography>{runs.map(run => <Box key={run.id}><Typography>{new Date(run.created_at).toLocaleString()} · {run.status} · folder: {run.payload.source_directory ?? "."}{run.payload.force ? " · full reprocessing" : ""}</Typography><Box component="pre" sx={{ whiteSpace: "pre-wrap" }}>{run.logs.join("\n")}</Box></Box>)}</Stack></Paper>;
}

