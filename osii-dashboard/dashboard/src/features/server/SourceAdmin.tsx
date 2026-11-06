import { useEffect, useState } from "react";
import { Alert, Box, Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { api } from "./api";

type Status = { mount_root: string; directory: string; available: boolean; readable: boolean;
  statistics: { documents: number; chunks: number; embedded_chunks: number };
  models: { chat_model?: string; embedding_model?: string }; extractor_url: string; ocr_configured: boolean };
type Listing = { path: string; items: { name: string; path: string; kind: string; size_bytes: number | null; readable: boolean }[]; next_cursor: number | null; truncated: boolean };

export function SourceAdmin() {
  const [status, setStatus] = useState<Status | null>(null);
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = async () => setStatus(await api<Status>("/api/admin/source"));
  const browse = async (path: string, cursor = 0) => {
    setBusy(true); setError("");
    try {
      const result = await api<Listing>(`/api/admin/source/browse?path=${encodeURIComponent(path)}&cursor=${cursor}`);
      setListing(current => cursor && current ? { ...result, items: [...current.items, ...result.items] } : result);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { void refresh().catch(e => setError(e.message)); void browse("."); }, []);
  const select = async () => {
    if (!listing) return;
    setBusy(true); setError(""); setNotice("");
    try {
      setStatus(await api<Status>("/api/admin/source", "PUT", { directory: listing.path }));
      setNotice("Source selection saved for future processing jobs. Existing documents and queued jobs are retained.");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <Stack spacing={3}>
    <Typography variant="h5">Source & status</Typography>
    {error && <Alert severity="error">{error}</Alert>}{notice && <Alert severity="success">{notice}</Alert>}
    {status && <Paper sx={{ p: 3 }}><Stack spacing={2} sx={{ overflowWrap: "anywhere" }}>
      <Stack direction="row" spacing={1} flexWrap="wrap"><Chip label={status.available && status.readable ? "Source available" : "Source unavailable or unreadable"} color={status.available && status.readable ? "success" : "error"} /><Chip label="PostgreSQL connected" /></Stack>
      <Typography>Mounted source root: <Box component="code">{status.mount_root}</Box></Typography>
      <Typography>Selected processing folder: <Box component="code">{status.directory}</Box></Typography>
      <Typography>{status.statistics.documents} indexed documents · {status.statistics.chunks} text chunks · {status.statistics.embedded_chunks} chunks with embeddings</Typography>
      <Typography>Chat model: {status.models.chat_model || "Not selected"}<br />Embedding model: {status.models.embedding_model || "Not selected"}</Typography>
      <Typography variant="body2" color="text.secondary">Extractor: {status.extractor_url} · OCR processor: {status.ocr_configured ? "configured" : "not configured"}. Scans without extracted text require OCR.</Typography>
      <Button sx={{ alignSelf: "start" }} onClick={() => void refresh().catch(e => setError(e.message))}>Refresh status</Button>
    </Stack></Paper>}
    <Paper sx={{ p: 3 }}><Stack spacing={2} sx={{ overflowWrap: "anywhere" }}>
      <Typography variant="h6">Browse source files</Typography>
      <Typography variant="body2">These are original files on the mounted share, including files that have not been processed. Choose a subfolder for future processing. Selecting a folder does not process or remove documents.</Typography>
      <Typography variant="body2" color="text.secondary">You can select subfolders within the mounted source root. Mounting a different share or filesystem requires an operator to update the deployment.</Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}><Button disabled={busy} onClick={() => void browse(".")}>Mount root</Button><Button disabled={busy || !listing || listing.path === "."} onClick={() => void browse(listing?.path.split("/").slice(0, -1).join("/") || ".")}>Up one folder</Button><Button variant="contained" disabled={busy || !listing} onClick={() => void select()}>Use this folder for processing</Button></Stack>
      <Typography component="code" sx={{ overflowWrap: "anywhere" }}>{listing?.path ?? "Loading source…"}</Typography>
      {listing?.truncated && <Alert severity="warning">This folder exceeds the 20,000-entry browsing limit. Split it into smaller subfolders to browse everything.</Alert>}
      {listing && !listing.items.length && <Typography color="text.secondary">No visible files or folders.</Typography>}
      {listing?.items.map(item => <Stack key={item.path} direction="row" spacing={2} alignItems="center">
        {item.kind === "directory" ? <Button disabled={busy} onClick={() => void browse(item.path)}>Folder: {item.name}</Button> : <Typography sx={{ flex: 1, overflowWrap: "anywhere" }}>{item.name}</Typography>}
        <Typography variant="caption">{item.kind === "directory" ? "Directory" : `${((item.size_bytes ?? 0) / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KiB`}{!item.readable && " · unreadable"}</Typography>
      </Stack>)}
      {listing?.next_cursor != null && <Button disabled={busy} onClick={() => void browse(listing.path, listing.next_cursor!)}>Load more source entries</Button>}
    </Stack></Paper>
  </Stack>;
}
