import {useState, type ChangeEvent} from "react";
import {Alert, Button, List, ListItem, ListItemText, Paper, Stack, Typography} from "@mui/material";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import {LocationBrowser, type PickedFile} from "../../../components/discovery/LocationBrowser";
import {uploadQueueFiles} from "../../../api/queue";

export function FileSelectionPanel({files, onFiles, title = "Select files"}: {files: PickedFile[]; onFiles: (files: PickedFile[]) => void; title?: string}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []); event.target.value = "";
    if (!selected.length) return;
    if (selected.length > 10000 || selected.some(file => file.size > 50 * 1024 ** 2) || selected.reduce((sum, file) => sum + file.size, 0) > 1024 ** 3) {
      setError("Choose up to 10,000 files, 50 MiB per file, and 1 GiB total."); return;
    }
    setBusy(true); setError("");
    try { const response = await uploadQueueFiles(selected); onFiles(response.uploads.map(file => ({path: file.path, name: file.name, size_bytes: file.size_bytes}))); }
    catch (error) {setError((error as Error).message);} finally {setBusy(false);}
  };
  return <Paper variant="outlined" sx={{p: 2}}><Stack spacing={1.5}>
    <Typography variant="h6" fontWeight={700}>{title}</Typography>
    <Stack direction="row" spacing={1}><Button variant="contained" startIcon={<FolderOutlinedIcon />} disabled={busy} onClick={() => setOpen(true)}>Browse files</Button><Button component="label" startIcon={<UploadFileOutlinedIcon />} disabled={busy}>Upload files<input hidden type="file" multiple onChange={event => void upload(event)} /></Button></Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {files.length > 0 && <><Typography fontWeight={600}>{files.length} selected {files.length === 1 ? "file" : "files"}</Typography><List dense sx={{maxHeight: 220, overflow: "auto"}}>{files.map(file => <ListItem key={file.path} secondaryAction={<Button size="small" onClick={() => onFiles(files.filter(item => item.path !== file.path))}>Remove</Button>}><ListItemText primary={file.name} secondary={file.path} sx={{overflowWrap: "anywhere", pr: 6}} /></ListItem>)}</List><Button sx={{alignSelf: "start"}} onClick={() => onFiles([])}>Clear selection</Button></>}
    <LocationBrowser open={open} initialPath={localStorage.getItem("osii:last-folder") || undefined} selected={files} onClose={() => setOpen(false)} onFiles={selected => {onFiles(selected); setOpen(false);}} />
  </Stack></Paper>;
}
