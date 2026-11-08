import { useEffect, useState } from "react";
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
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

export { Intake } from "./Intake";
