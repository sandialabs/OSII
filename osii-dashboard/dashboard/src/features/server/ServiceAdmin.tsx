import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, Stack, Typography, Box } from "@mui/material";
import { ServiceRow } from "../admin/components/ServiceRow";
import type { ManagedCapabilityService } from "../../api/types";
import { api } from "./api";

type Service = ManagedCapabilityService & { can_logs?: boolean };
type Action = "start" | "stop" | "restart";
export function ServiceAdmin() {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["server", "services"], queryFn: () => api<{ services: Service[] }>("/api/admin/services"), refetchInterval: 10000, retry: false });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState<{ service: Service; action: Action } | null>(null);
  const [logs, setLogs] = useState<{ title: string; lines: string[] } | null>(null);
  const action = async (service: Service, operation: Action) => {
    setBusy(service.id); setError(""); setNotice(""); setPending(null);
    try {
      await api(`/api/admin/services/${encodeURIComponent(service.id)}/${operation}`, "POST", {});
      setNotice(`${service.display_name}: ${operation} requested. Status refreshes automatically.`);
      await client.invalidateQueries({ queryKey: ["server", "services"] });
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const showLogs = async (service: Service) => {
    setBusy(service.id); setError("");
    try { const data = await api<{ lines: string[] }>(`/api/admin/services/${encodeURIComponent(service.id)}/logs`); setLogs({ title: service.display_name, lines: data.lines }); }
    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  return <Stack spacing={2}>
    <Typography variant="h6" fontWeight={700}>Service status</Typography>
    <Typography color="text.secondary">Manage tools deployed on this server. Built-in synthesis/enrichment run inside Core; externally hosted models and processors are managed by their operators.</Typography>
    <Button onClick={() => void status.refetch()} disabled={status.isFetching} sx={{ alignSelf: "start" }}>Refresh service status</Button>
    {status.isFetching && <LinearProgress aria-label="Checking services" />}
    {status.isError && <Alert severity="warning">{(status.error as Error).message}. Processor health remains available in the component drawers below.</Alert>}
    {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}
    {notice && <Alert severity="info" onClose={() => setNotice("")}>{notice}</Alert>}
    {!status.isError && status.data?.services.map(service => <Stack key={service.id} spacing={0.5}>
      <ServiceRow service={service} busy={busy !== null} onAction={operation => operation === "start" ? void action(service, operation) : setPending({ service, action: operation })}
        onLogs={service.can_logs ? () => void showLogs(service) : undefined} />
      {service.detail && <Typography variant="caption" color="text.secondary">{service.detail}</Typography>}
    </Stack>)}
    <Dialog open={pending !== null} onClose={() => setPending(null)}><DialogTitle>{pending?.action === "stop" ? "Stop" : "Restart"} {pending?.service.display_name}?</DialogTitle>
      <DialogContent>This can interrupt an active extraction and cause the current document to fail. Pause processing in Intake and wait for the current document to finish first. Queued jobs and saved results are retained.</DialogContent>
      <DialogActions><Button onClick={() => setPending(null)}>Cancel</Button><Button color="error" disabled={busy !== null} onClick={() => pending && void action(pending.service, pending.action)}>Confirm {pending?.action}</Button></DialogActions>
    </Dialog>
    <Dialog open={logs !== null} onClose={() => setLogs(null)} fullWidth maxWidth="md"><DialogTitle>{logs?.title} logs</DialogTitle><DialogContent>
      <Typography variant="caption">Up to 80 lines from the last hour, capped at 64 KiB. Credential patterns are redacted; logs may include document names or content.</Typography>
      <Box component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 420, overflow: "auto", bgcolor: "action.hover", p: 2 }}>{logs?.lines.join("\n") || "No recent log entries."}</Box>
    </DialogContent><DialogActions><Button onClick={() => setLogs(null)}>Close</Button></DialogActions></Dialog>
  </Stack>;
}
