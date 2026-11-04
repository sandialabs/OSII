import { useEffect, useState, type FormEvent } from "react";
import { Alert, AppBar, Autocomplete, Box, Button, Chip, Container, Dialog, DialogContent, DialogTitle, Divider, MenuItem, Paper, Stack, Tab, Tabs, TextField, Toolbar, Typography } from "@mui/material";

type User = { id: string; username: string; role: "reader" | "curator" | "admin"; active: boolean; must_change_password: boolean };
type Doc = { file_id: string; filename: string; source_relpath: string; text?: string; media_type?: string };
type Hit = Doc & { chunk_id: string; snippet: string; char_start: number; char_end: number; source_origin: unknown };
type Model = { id: string; name: string; capabilities: string[] };

async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const csrf = document.cookie.split("; ").find(value => value.startsWith("osii_csrf="))?.split("=").slice(1).join("=") ?? "";
  const response = await fetch(path, { method, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") window.dispatchEvent(new Event("osii-session-expired"));
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  }
  return data as T;
}

function SignIn({ onUser, changing = false }: { onUser: (user: User | null) => void; changing?: boolean }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (changing) { await api("/api/auth/password", "POST", { current_password: password, new_password: newPassword }); onUser(null); }
      else { const result = await api<{ user: User }>("/api/auth/login", "POST", { username, password }); onUser(result.user); }
    } catch (e) { setError((e as Error).message); }
    finally { setPassword(""); setBusy(false); }
  };
  return <Container maxWidth="sm" sx={{ pt: 10 }}><Paper sx={{ p: 4 }}><Stack component="form" spacing={2} onSubmit={submit}>
    <Typography variant="h4">OSII</Typography><Typography variant="h6">{changing ? "Change your temporary password" : "Sign in to your library"}</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    {!changing && <TextField label="Username" autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} />}
    <TextField label={changing ? "Current password" : "Password"} type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
    {changing && <TextField label="New password" helperText="Use 15–128 characters." type="password" autoComplete="new-password" required value={newPassword} onChange={e => setNewPassword(e.target.value)} inputProps={{ minLength: 15, maxLength: 128 }} />}
    <Button type="submit" variant="contained" disabled={busy}>{changing ? "Change password and sign in again" : "Sign in"}</Button>
    <Typography color="text.secondary" variant="body2">Accounts are provided by your library administrator.</Typography>
  </Stack></Paper></Container>;
}

function ModelAdmin() {
  const [config, setConfig] = useState({ chat_model: "", embedding_model: "", base_url: "", credential_present: false });
  const [models, setModels] = useState<Model[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { void api<typeof config>("/api/admin/models").then(setConfig).catch(e => setError(e.message)); }, []);
  const action = async (kind: "discover" | "save" | "test") => {
    setBusy(true); setError(""); setNotice("");
    try {
      if (kind === "discover") { const result = await api<{ models: Model[] }>("/api/admin/models/catalog"); setModels(result.models); setNotice(`Found ${result.models.length} models. Catalog discovery does not test generation or billing access.`); }
      else if (kind === "save") { await api("/api/admin/models", "PUT", { chat_model: config.chat_model, embedding_model: config.embedding_model }); setNotice("Model selections saved. Changing embeddings requires reprocessing the library."); }
      else { const result = await api<Record<string, { configured: boolean; ok?: boolean; detail?: string }>>("/api/admin/models/test", "POST", {}); setNotice(Object.entries(result).map(([name, check]) => `${name}: ${!check.configured ? "not selected" : check.ok ? "invocation passed" : check.detail}`).join(" · ")); }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <Paper sx={{ p: 3 }}><Stack spacing={2}><Typography variant="h6">Model connection</Typography>
    <Typography>{config.base_url}</Typography><Chip sx={{ alignSelf: "start" }} label={config.credential_present ? "Provider key configured" : "Provider key missing"} />
    <Typography variant="body2" color="text.secondary">The endpoint and provider key are managed by the deployment. Only administrators select models.</Typography>
    {error && <Alert severity="error">{error}</Alert>}{notice && <Alert severity="info">{notice}</Alert>}
    {(["chat", "embedding"] as const).map(kind => <Autocomplete key={kind} freeSolo options={models.filter(m => !m.capabilities.length || m.capabilities.includes(kind)).map(m => m.id)} value={config[`${kind}_model`]} onChange={(_, value) => setConfig({ ...config, [`${kind}_model`]: value ?? "" })} onInputChange={(_, value, reason) => { if (reason === "input") setConfig(current => ({ ...current, [`${kind}_model`]: value })); }} getOptionLabel={id => { const model = models.find(m => m.id === id); return model ? `${model.name} — ${id}` : id; }} renderInput={params => <TextField {...params} label={kind === "chat" ? "Language model ID" : "Embedding model ID (optional)"} helperText="Choose a discovered model or enter its exact API ID." />} />)}
    <Stack direction="row" spacing={1}><Button disabled={busy} onClick={() => void action("discover")}>Discover models</Button><Button variant="contained" disabled={busy} onClick={() => void action("save")}>Save selection</Button><Button disabled={busy} onClick={() => void action("test")}>Test selected models</Button></Stack>
  </Stack></Paper>;
}

function UserAdmin() {
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

function Intake() {
  const [runs, setRuns] = useState<{ id: string; status: string; logs: string[] }[]>([]);
  const [error, setError] = useState("");
  const refresh = () => api<{ runs: typeof runs }>("/api/runs").then(r => setRuns(r.runs));
  useEffect(() => { void refresh().catch(e => setError(e.message)); const t = window.setInterval(() => { void refresh().catch(e => setError(e.message)); }, 5000); return () => window.clearInterval(t); }, []);
  return <Paper sx={{ p: 3 }}><Stack spacing={2}><Typography variant="h6">Shared dataset processing</Typography><Typography>Process the source folder configured by the deployment. Originals remain unchanged.</Typography>{error && <Alert severity="error">{error}</Alert>}<Button variant="contained" onClick={() => void api("/api/admin/intake", "POST", {}).then(refresh).catch(e => setError(e.message))}>Process shared dataset</Button><Button onClick={() => void api("/api/admin/intake", "POST", { force: true }).then(refresh).catch(e => setError(e.message))}>Reprocess all documents</Button><Typography variant="body2" color="text.secondary">Reprocessing repeats extraction and any configured embedding calls.</Typography>{runs.map(run => <Box key={run.id}><Typography>{run.id} · {run.status}</Typography><Box component="pre" sx={{ whiteSpace: "pre-wrap" }}>{run.logs.join("\n")}</Box></Box>)}</Stack></Paper>;
}

function Workspace({ user, onLogout, onPassword }: { user: User; onLogout: () => void; onPassword: () => void }) {
  const [tab, setTab] = useState("library");
  const [docs, setDocs] = useState<Doc[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [hits, setHits] = useState<Hit[]>([]);
  const [answer, setAnswer] = useState("");
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [scope, setScope] = useState<Record<string, string>>({ scope_type: "root" });
  const [collections, setCollections] = useState<{ id: string; name: string }[]>([]);
  const [collectionName, setCollectionName] = useState("");
  const [selected, setSelected] = useState<Doc | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState("");
  useEffect(() => { void api<{ items: Doc[]; next_cursor: string | null }>("/api/catalog/files?limit=500").then(r => { setDocs(r.items); setNextCursor(r.next_cursor); }).catch(e => setError(e.message)); void api<{ items: typeof collections }>("/api/collections").then(r => setCollections(r.items)).catch(e => setError(e.message)); }, [tab]);
  const loadMore = () => api<{ items: Doc[]; next_cursor: string | null }>(`/api/catalog/files?limit=500&cursor=${encodeURIComponent(nextCursor ?? "")}`).then(r => { setDocs(current => [...current, ...r.items]); setNextCursor(r.next_cursor); }).catch(e => setError(e.message));
  const open = async (id: string) => { try { setSelected(await api<Doc>(`/api/objects/${id}`)); } catch (e) { setError((e as Error).message); } };
  const search = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setAnswer("");
    try {
      if (tab === "chat") {
        const result = await api<{ answer: string; citations: Hit[]; provider: string; fallback_used: boolean; retrieval_mode: string }>("/api/chat", "POST", { query, history, scope });
        setAnswer(result.answer); setHits(result.citations); setDetail(`${result.provider} · ${result.retrieval_mode}${result.fallback_used ? " · extractive fallback" : ""}`);
        setHistory(current => [...current, { role: "user", content: query }, { role: "assistant", content: result.answer }].slice(-12));
      } else {
        const result = await api<{ results: Hit[]; channels_used: string[]; warning?: string }>("/api/search", "POST", { query, mode, scope });
        setHits(result.results); setDetail(result.warning || result.channels_used.join(" · ") || "No matching evidence");
      }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const curator = user.role !== "reader";
  return <><AppBar position="static"><Toolbar><Typography variant="h6" sx={{ flex: 1 }}>OSII · Shared library</Typography><Typography sx={{ mr: 2 }}>{user.username}</Typography><Button color="inherit" onClick={onPassword}>Password</Button><Button color="inherit" onClick={onLogout}>Sign out</Button></Toolbar></AppBar>
    <Container maxWidth="lg" sx={{ py: 3 }}><Stack spacing={3}><Tabs value={tab} onChange={(_, value) => { setTab(value); setError(""); setHits([]); setAnswer(""); }}><Tab value="library" label="Library" /><Tab value="search" label="Search" /><Tab value="chat" label="Chat" />{curator && <Tab value="processing" label="Processing" />}{user.role === "admin" && <Tab value="admin" label="Administration" />}</Tabs>
      {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}
      {tab === "library" && <><Typography variant="h5">Shared dataset</Typography>{!docs.length && <Alert severity="info">The library is being prepared. Contact your administrator if it remains empty.</Alert>}{docs.map(doc => <Paper key={doc.file_id} sx={{ p: 2 }}><Button onClick={() => void open(doc.file_id)}>{doc.filename}</Button><Typography color="text.secondary">{doc.source_relpath}</Typography><Button size="small" onClick={() => { setScope({ scope_type: "folder", folder_id: doc.source_relpath.includes("/") ? doc.source_relpath.slice(0, doc.source_relpath.lastIndexOf("/")) : "." }); setTab("search"); }}>Search this folder</Button></Paper>)}
        {nextCursor && <Button onClick={() => void loadMore()}>Load more documents</Button>}
        {curator && <Stack direction="row" spacing={1}><TextField label="Shared collection name" value={collectionName} onChange={e => setCollectionName(e.target.value)} /><Button onClick={() => void api("/api/collections", "POST", { name: collectionName, members: docs.map(d => d.file_id) }).then(() => api<{ items: typeof collections }>("/api/collections")).then(r => setCollections(r.items)).catch(e => setError(e.message))}>Create collection from listed files</Button></Stack>}
        {collections.map(c => <Button key={c.id} onClick={() => { setScope({ scope_type: "collection", collection_id: c.id }); setTab("search"); }}>{c.name}</Button>)}
      </>}
      {(tab === "search" || tab === "chat") && <><Stack component="form" spacing={2} onSubmit={search}><Typography variant="h5">{tab === "chat" ? "Ask the library" : "Search the library"}</Typography><Stack direction="row" spacing={1}><Chip label={scope.scope_type === "root" ? "Entire library" : `Scope: ${scope.scope_type}`} onDelete={scope.scope_type === "root" ? undefined : () => setScope({ scope_type: "root" })} />{tab === "chat" && <Button onClick={() => { setHistory([]); setAnswer(""); setHits([]); }}>New conversation</Button>}</Stack><TextField label={tab === "chat" ? "Question" : "Search terms or question"} value={query} onChange={e => setQuery(e.target.value)} required inputProps={{ maxLength: 4000 }} />{tab === "search" && <TextField select label="Retrieval" value={mode} onChange={e => setMode(e.target.value)}>{["hybrid", "lexical", "semantic"].map(m => <MenuItem key={m} value={m}>{m}</MenuItem>)}</TextField>}<Button type="submit" variant="contained" disabled={busy}>{busy ? "Working…" : tab === "chat" ? "Ask" : "Search"}</Button></Stack>{detail && <Typography color="text.secondary">{detail}</Typography>}{answer && <Paper sx={{ p: 3, whiteSpace: "pre-wrap" }}>{answer}</Paper>}{hits.map((hit, i) => <Paper key={hit.chunk_id ?? i} sx={{ p: 2 }}><Button onClick={() => void open(hit.file_id)}>{hit.filename}</Button><Typography sx={{ whiteSpace: "pre-wrap" }}>{hit.snippet}</Typography><Typography variant="caption">Source characters {hit.char_start}–{hit.char_end}</Typography></Paper>)}</>}
      {tab === "processing" && curator && <Intake />}{tab === "admin" && user.role === "admin" && <><ModelAdmin /><UserAdmin /></>}
    </Stack></Container>
    <Dialog open={Boolean(selected)} onClose={() => setSelected(null)} fullWidth maxWidth="lg"><DialogTitle>{selected?.filename}</DialogTitle><DialogContent><Stack spacing={2}><Button component="a" href={`/api/objects/${selected?.file_id}/source`} target="_blank" rel="noopener">Open original source</Button>{selected?.media_type === "application/pdf" && <Box component="iframe" title="Source PDF" src={`/api/objects/${selected.file_id}/source`} sx={{ height: 500, border: 0 }} />}<Divider /><Typography variant="h6">Extracted evidence</Typography><Typography component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit" }}>{selected?.text}</Typography></Stack></DialogContent></Dialog>
  </>;
}

export function ServerApp() {
  const [user, setUser] = useState<User | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [changing, setChanging] = useState(false);
  useEffect(() => {
    void api<{ user: User }>("/api/auth/me").then(r => setUser(r.user)).catch(() => setUser(null)).finally(() => setLoaded(true));
    const expired = () => { setUser(null); setChanging(false); };
    window.addEventListener("osii-session-expired", expired);
    return () => window.removeEventListener("osii-session-expired", expired);
  }, []);
  if (!loaded) return <Typography sx={{ p: 4 }}>Opening OSII…</Typography>;
  if (!user) return <SignIn onUser={setUser} />;
  if (user.must_change_password || changing) return <SignIn changing onUser={u => { setUser(u); setChanging(false); }} />;
  return <Workspace key={user.id} user={user} onPassword={() => setChanging(true)} onLogout={() => void api("/api/auth/logout", "POST", {}).finally(() => setUser(null))} />;
}
