import { useState } from "react";
import { Alert, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiJson } from "../../../api/client";
import { controlCapabilityService } from "../../../api/queue";
import type { ManagedCapabilityService, ProcessorConfigSchema } from "../../../api/types";
import { ProcessorConfigInput } from "../../queue/components/ProcessorConfigInput";

type ModuleSettings = {
  id: string; processor_id: string; schema: ProcessorConfigSchema;
  config: Record<string, unknown>; environment_overrides: string[];
  credential?: { present: boolean; writable: boolean } | null;
};

export function ProcessorStartupSettings({ processorId, service }: { processorId: string; service?: ManagedCapabilityService }) {
  const client = useQueryClient();
  const settings = useQuery({
    queryKey: ["admin", "processor-startup-settings"],
    queryFn: () => apiJson<{ processors: ModuleSettings[] }>("/api/admin/processor-settings/startup"),
  });
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [key, setKey] = useState("");
  const [notice, setNotice] = useState<{ ok: boolean; text: string }>();
  const [saving, setSaving] = useState(false);
  const module = settings.data?.processors.find(item => item.processor_id === processorId);
  if (!module) return settings.isError ? <Alert severity="error">{settings.error.message}</Alert> : null;
  const changed = Object.keys(draft).length > 0;
  const restart = changed && Boolean(service?.can_restart);
  const save = async () => {
    setSaving(true); setNotice(undefined);
    const path = "/api/admin/processor-settings/startup/" + encodeURIComponent(module.id);
    try {
      if (key.trim()) {
        await apiJson(path + "/credential", { method: "PUT", json: { api_key: key } });
        setKey("");
      }
      if (changed) {
        await apiJson(path, { method: "PUT", json: { config: { ...module.config, ...draft } } });
        setDraft({});
      }
      if (restart && service) await controlCapabilityService(service.id, "restart");
      setNotice({ ok: true, text: changed && !restart ? "Saved. Start or restart the processor to apply the settings." : "Connection settings saved." });
    } catch (error) { setNotice({ ok: false, text: (error as Error).message }); }
    finally {
      await client.invalidateQueries({ queryKey: ["admin"] });
      setSaving(false);
    }
  };
  return <Paper component="form" variant="outlined" sx={{ p: 2 }} onSubmit={event => { event.preventDefault(); void save(); }}>
    <Stack spacing={1.5}>
      <Typography component="h2" variant="h6">Upstream settings</Typography>
      {Object.entries(module.schema.properties ?? {}).map(([name, prop]) => <ProcessorConfigInput key={name} name={name}
        property={prop} value={draft[name] ?? module.config[name] ?? prop.default}
        disabled={module.environment_overrides.includes(name)}
        onChange={value => setDraft(current => ({ ...current, [name]: value }))} />)}
      {module.credential && <TextField size="small" label="API key" type="password" autoComplete="off"
        disabled={!module.credential.writable} placeholder={module.credential.present ? "••••••••" : undefined}
        value={key} onChange={event => setKey(event.target.value)} />}
      {module.environment_overrides.length > 0 && <Typography variant="caption">Startup environment overrides {module.environment_overrides.join(", ")}.</Typography>}
      {notice && <Alert severity={notice.ok ? "success" : "error"}>{notice.text}</Alert>}
      <Button type="submit" variant="contained" disabled={saving || (!changed && !key.trim())} sx={{ alignSelf: "start" }}>
        {saving ? "Saving…" : restart ? "Save & restart" : "Save upstream settings"}
      </Button>
    </Stack>
  </Paper>;
}
