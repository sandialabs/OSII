import { useState } from "react";
import { Alert, Button, Dialog, DialogContent, DialogTitle, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { api, type Collection, type User } from "./api";

type Props = { collections: Collection[]; refresh: () => Promise<void>; fail: (e: unknown) => void };
export function CollectionSelection({ collections, refresh, fail, selected, clear, current }: Props & { selected: Set<string>; clear: () => void; current?: Collection }) {
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (kind: "create" | "add" | "remove") => {
    setBusy(true);
    try {
      const collection = kind === "remove" ? current : collections.find(c => c.id === target);
      if (kind === "create") await api("/api/collections", "POST", { name, members: [...selected] });
      else if (collection) {
        const members = kind === "add" ? [...new Set([...collection.members, ...selected])] : collection.members.filter(id => !selected.has(id));
        await api(`/api/collections/${collection.id}`, "PUT", { ...collection, members });
      }
      await refresh(); clear(); setName(""); setTarget("");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return <Paper sx={{ p: 2 }}><Stack spacing={2}>
    <Typography variant="h6">{selected.size} selected documents</Typography>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
      <TextField label="New private collection name" value={name} onChange={e => setName(e.target.value)} inputProps={{ maxLength: 150 }} />
      <Button variant="contained" disabled={busy || !name.trim()} onClick={() => void save("create")}>Create private collection</Button><Button onClick={clear}>Clear selection</Button>
    </Stack>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
      <TextField select label="Existing collection" sx={{ minWidth: 220 }} value={target} onChange={e => setTarget(e.target.value)}><MenuItem value="">Choose a collection</MenuItem>{collections.filter(c => c.can_manage).map(c => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>
      <Button disabled={busy || !target} onClick={() => void save("add")}>Add selected documents</Button>
      {current?.can_manage && <Button disabled={busy} onClick={() => void save("remove")}>Remove selected from this collection</Button>}
    </Stack>
  </Stack></Paper>;
}

export function Collections({ collections, refresh, fail, user, browse, choose }: Props & { user: User; browse: (id: string, page: string) => void; choose: () => void }) {
  const [editing, setEditing] = useState<Collection | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async (remove = false) => {
    if (!editing) return;
    if (remove && !window.confirm(`Delete collection “${editing.name}”? Source documents are retained.`)) return;
    setBusy(true);
    try { await api(`/api/collections/${editing.id}`, remove ? "DELETE" : "PUT", remove ? undefined : editing); await refresh(); setEditing(null); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  return <Stack spacing={2}>
    <Typography variant="h5">Collections</Typography>
    <Typography color="text.secondary">Your collections are private by default. Curators and administrators can publish their collections for everyone. Collections group shared documents; they do not restrict access to those source files.</Typography>
    <Button sx={{ alignSelf: "start" }} onClick={choose}>Choose files in the library</Button>
    {!collections.length && <Alert severity="info">Select documents in the library, search results, or topic explorer to create a collection.</Alert>}
    {collections.map(c => <Paper key={c.id} sx={{ p: 2 }}><Stack spacing={1}>
      <Button component="a" href={`/research?collection_id=${encodeURIComponent(c.id)}`} sx={{ alignSelf: "start" }}>Write a research report</Button>
      <Typography variant="h6">{c.name}</Typography><Typography>{c.description}</Typography>
      <Typography variant="body2" color="text.secondary">{c.visibility === "private" ? "Private to you" : "Shared with everyone"} · {c.members.length} document references</Typography>
      <Stack direction="row" flexWrap="wrap" spacing={1}>{[["library", "Browse"], ["search", "Search"], ["chat", "Chat"], ["topics", "Explore topics"]].map(([page, label]) => <Button key={page} onClick={() => browse(c.id, page)}>{label}</Button>)}{c.can_manage && <Button onClick={() => setEditing({ ...c })}>Edit collection</Button>}</Stack>
    </Stack></Paper>)}
    <Dialog open={Boolean(editing)} onClose={() => setEditing(null)} fullWidth maxWidth="sm"><DialogTitle>Edit collection</DialogTitle><DialogContent>{editing && <Stack spacing={2} sx={{ pt: 1 }}>
      <TextField label="Collection name" value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} inputProps={{ maxLength: 150 }} />
      <TextField label="Description" multiline value={editing.description} onChange={e => setEditing({ ...editing, description: e.target.value })} inputProps={{ maxLength: 4000 }} />
      {user.role !== "reader" && <TextField select label="Visibility" value={editing.visibility} onChange={e => setEditing({ ...editing, visibility: e.target.value as Collection["visibility"] })}>{editing.owner_id === user.id && <MenuItem value="private">Private to you</MenuItem>}<MenuItem value="shared">Shared with everyone</MenuItem></TextField>}
      <Button disabled={busy || !editing.name.trim()} variant="contained" onClick={() => void save()}>Save collection</Button><Button color="error" disabled={busy} onClick={() => void save(true)}>Delete collection</Button>
    </Stack>}</DialogContent></Dialog>
  </Stack>;
}
