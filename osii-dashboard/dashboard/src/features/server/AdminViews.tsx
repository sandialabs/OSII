import { useEffect, useState } from "react";
import { Alert, Box, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { api, type User } from "./api";

export { ModelAdmin } from "./ModelAdmin";

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

