import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Checkbox, FormControlLabel, Container, Paper, Stack, TextField, Typography } from "@mui/material";
import { api, type User } from "./api";
import { Workspace } from "./Workspace";

function SignIn({ onUser, changing = false }: { onUser: (user: User | null) => void; changing?: boolean }) {
  const [remember, setRemember] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (changing) { await api("/api/auth/password", "POST", { current_password: password, new_password: newPassword }); onUser(null); }
      else { const result = await api<{ user: User }>("/api/auth/login", "POST", { username, password, remember }); onUser(result.user); }
    } catch (e) { setError((e as Error).message); }
    finally { setPassword(""); setBusy(false); }
  };
  return <Container maxWidth="sm" sx={{ pt: 10 }}><Paper sx={{ p: 4 }}><Stack component="form" spacing={2} onSubmit={submit}>
    <Typography variant="h4">OSII</Typography><Typography variant="h6">{changing ? "Change your temporary password" : "Sign in to your library"}</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    {!changing && <TextField label="Username" autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} />}
    <TextField label={changing ? "Current password" : "Password"} type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
    {changing && <TextField label="New password" helperText="Use 15–128 characters." type="password" autoComplete="new-password" required value={newPassword} onChange={e => setNewPassword(e.target.value)} inputProps={{ minLength: 15, maxLength: 128 }} />}
    {!changing && <FormControlLabel control={<Checkbox checked={remember} onChange={e => setRemember(e.target.checked)} />} label="Stay signed in on this device" />}
    <Button type="submit" variant="contained" disabled={busy}>{changing ? "Change password and sign in again" : "Sign in"}</Button>
    <Typography color="text.secondary" variant="body2">Accounts are provided by your library administrator.</Typography>
  </Stack></Paper></Container>;
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
