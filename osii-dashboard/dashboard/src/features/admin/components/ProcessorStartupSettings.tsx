import { useState } from "react";
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiJson } from "../../../api/client";
import type { ProcessorConfigSchema } from "../../../api/types";
import { ProcessorConfigInput } from "../../queue/components/ProcessorConfigInput";

type ModuleSettings = {id: string; processor_id: string; display_name: string; schema: ProcessorConfigSchema; config: Record<string, unknown>; environment_overrides: string[]};
export function ProcessorStartupSettings({processorId}: {processorId: string}) {
  const client = useQueryClient();
  const settings = useQuery({queryKey: ["admin", "processor-startup-settings"], queryFn: () => apiJson<{path: string; processors: ModuleSettings[]}>("/api/admin/processor-settings/startup")});
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const module = settings.data?.processors.find(item => item.processor_id === processorId);
  if (settings.isError) return <Alert severity="error">Startup settings: {(settings.error as Error).message}</Alert>;
  if (!module) return null;
  const save = async () => {
    setSaving(true); setError("");
    try {
      await apiJson(`/api/admin/processor-settings/startup/${module.id}`, {method: "PUT", json: {config: draft}});
      await client.invalidateQueries({queryKey: ["admin", "processor-startup-settings"]});
      setOpen(false);
    } catch (error) { setError((error as Error).message); }
    finally { setSaving(false); }
  };
  return <><Button size="small" sx={{alignSelf: "flex-start", px: 0}} onClick={() => {
    setDraft(Object.fromEntries(Object.entries(module.schema.properties ?? {}).map(([name, prop]) => [name, module.config[name] ?? prop.default]))); setError(""); setOpen(true);
  }}>Startup settings</Button><Dialog open={open} onClose={() => !saving && setOpen(false)} fullWidth maxWidth="sm"><DialogTitle>{module.display_name} startup</DialogTitle><DialogContent><Stack spacing={1.5} sx={{pt: 1}}>
    <Alert severity="info">Restart this service from Setup after saving. Running jobs keep their current configuration.</Alert>
    {module.environment_overrides.length ? <Alert severity="warning">Startup environment overrides these saved fields: {module.environment_overrides.join(", ")}. Remove those overrides to use Setup.</Alert> : null}
    {Object.entries(module.schema.properties ?? {}).map(([name, property]) => <ProcessorConfigInput key={name} name={name} property={property} value={draft[name]} onChange={value => setDraft({...draft, [name]: value})} />)}
    <Typography variant="caption" sx={{overflowWrap: "anywhere"}}>Saved in: <code>{settings.data?.path}</code></Typography>
    {error ? <Alert severity="error">{error}</Alert> : null}
  </Stack></DialogContent><DialogActions><Button disabled={saving} onClick={() => setOpen(false)}>Cancel</Button><Button disabled={saving} onClick={() => void save()}>Save startup settings</Button></DialogActions></Dialog></>;
}
