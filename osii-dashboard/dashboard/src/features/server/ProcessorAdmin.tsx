import { useEffect, useState } from "react";
import { Alert, Button, Chip, Paper, Stack, TextField, Typography } from "@mui/material";
import { api } from "./api";
export type ProcessorStatus = { id: string; display_name: string; kind: string; available: boolean; detail?: string; health?: string; base_url?: string; description?: string };
export function ProcessorAdmin({ queue }: { queue: (processor: ProcessorStatus) => void }) {
  const [rows,setRows]=useState<ProcessorStatus[]>([]);
  const [urls,setUrls]=useState(""); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
  const refresh=async()=>{ setBusy(true);setError("");try {const r=await api<{processors:ProcessorStatus[];urls:string[]}>("/api/admin/processors");setRows(r.processors);setUrls(r.urls.join("\n"));}catch(e){setError((e as Error).message);}finally{setBusy(false);} };
  useEffect(()=>{void refresh();},[]);
  const save=async()=>{setBusy(true);setError("");try {await api("/api/admin/processors","PUT",{urls:urls.split("\n").map(s=>s.trim()).filter(Boolean)});await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);} };
  return <Stack spacing={2}><Typography variant="h5">Processors & Toolbox</Typography>
    <Typography color="text.secondary">Health and availability of configured services. Choose Queue to select files and review a staged plan. Checking health does not process documents.</Typography>
    {error&&<Alert severity="error">{error}</Alert>}<Button color="secondary" disabled={busy} onClick={()=>void refresh()}>{busy?"Checking services…":"Refresh health"}</Button>
    {rows.map(row=><Paper key={`${row.kind}:${row.id}:${row.base_url}`} variant="outlined" sx={{p:2}}><Stack spacing={1}>
      <Stack direction="row" spacing={1} alignItems="center"><Typography fontWeight={700}>{row.display_name}</Typography><Chip size="small" label={row.available?row.health==="built_in"?"Built in":"Ready":"Unavailable"} color={row.available?"success":"error"}/><Chip size="small" label={row.kind}/></Stack>
      <Typography variant="body2">{row.description}</Typography><Typography variant="caption" color="text.secondary">{row.base_url||"Runs inside Core using the shared Processor SDK implementation"}</Typography>
      {row.detail&&<Typography variant="body2" color="text.secondary">{row.detail}</Typography>}
      {row.kind!=="embedder"&&row.kind!=="unavailable"&&<Button color="secondary" variant="outlined" disabled={!row.available} sx={{alignSelf:"start"}} onClick={()=>queue(row)}>Queue {row.kind==="extractor"?"extraction":row.kind==="synthesizer"?"synthesis":"enrichment"}</Button>}
      {row.kind==="embedder"&&<Typography variant="caption">Select embedding services under Models.</Typography>}
    </Stack></Paper>)}
    <Paper variant="outlined" sx={{p:2}}><Stack spacing={1}><Typography variant="h6">Optional Toolbox connections</Typography><Typography variant="body2">Add the base URLs of separately running Processor API services, one per line. This registers services; it does not install or launch them. Native extraction and the configured OCR fallback are also listed above.</Typography><TextField multiline minRows={3} label="Processor API endpoints" value={urls} onChange={e=>setUrls(e.target.value)}/><Button color="secondary" disabled={busy} onClick={()=>void save()}>Save connections and check health</Button></Stack></Paper>
  </Stack>;
}
