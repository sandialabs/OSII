import { useState } from "react";
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiJson } from "../../../api/client";

type Defaults = {preset: string; chunk_size: number; chunk_overlap: number; presets: {id: string; label: string}[]};

export function IntakeDefaults({path}: {path?: string}) {
  const client = useQueryClient();
  const defaults = useQuery({queryKey: ["intake", "defaults"], queryFn: () => apiJson<Defaults>("/api/intake/defaults")});
  const [draft, setDraft] = useState<Pick<Defaults, "preset" | "chunk_size" | "chunk_overlap"> | null>(null);
  const [help, setHelp] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{severity: "success" | "error"; text: string} | null>(null);
  const value = draft ?? defaults.data;
  const save = async () => {
    if (!value) return;
    setSaving(true); setMessage(null);
    try {
      await apiJson("/api/intake/defaults", {method: "PUT", json: {preset: value.preset, chunk_size: value.chunk_size, chunk_overlap: value.chunk_overlap}});
      await client.invalidateQueries({queryKey: ["intake", "defaults"]});
      setDraft(null); setMessage({severity: "success", text: "Defaults saved for new Intake sessions."});
    } catch (error) { setMessage({severity: "error", text: (error as Error).message}); }
    finally { setSaving(false); }
  };
  return <Paper variant="outlined" sx={{p: 1.5}}><Stack spacing={1}>
    <Stack direction="row" alignItems="center"><Typography fontWeight={700}>Intake defaults</Typography><IconButton aria-label="About Intake defaults" onClick={() => setHelp(true)}><HelpOutlineIcon fontSize="small" /></IconButton></Stack>
    {defaults.isError ? <Alert severity="error">{(defaults.error as Error).message}</Alert> : null}
    {value ? <Stack direction={{xs: "column", md: "row"}} spacing={1} alignItems={{md: "center"}}>
      <TextField select size="small" label="Processing preset" value={value.preset} onChange={event => setDraft({...value, preset: event.target.value})} sx={{minWidth: 230}}>{defaults.data?.presets.map(p => <MenuItem key={p.id} value={p.id}>{p.label}</MenuItem>)}</TextField>
      <TextField size="small" type="number" label="Chunk characters" value={value.chunk_size} inputProps={{min: 1}} onChange={event => setDraft({...value, chunk_size: Number(event.target.value)})} />
      <TextField size="small" type="number" label="Overlap characters" value={value.chunk_overlap} inputProps={{min: 0}} onChange={event => setDraft({...value, chunk_overlap: Number(event.target.value)})} />
      <Button disabled={!draft || saving} onClick={() => void save()}>Save defaults</Button>
    </Stack> : null}
    {message ? <Alert severity={message.severity} onClose={() => setMessage(null)}>{message.text}</Alert> : null}
  </Stack><Dialog open={help} onClose={() => setHelp(false)} fullWidth maxWidth="sm"><DialogTitle>Intake defaults</DialogTitle><DialogContent><Stack spacing={1}>
    <Typography>Choose the starting preset and embedding chunk sizes. You can change them for each run. Saving does not queue files or change an existing run or open selection.</Typography>
    <Typography>Readers, writing models, enrichment methods, and their settings are configured in the sections below. Saved defaults replace older OSII_INTAKE settings from the startup environment for the fields you save.</Typography>
    <Typography variant="body2" sx={{overflowWrap: "anywhere"}}>Saved in: <code>{path ?? "processors.toml"}</code></Typography>
  </Stack></DialogContent><DialogActions><Button onClick={() => setHelp(false)}>Close</Button></DialogActions></Dialog></Paper>;
}
