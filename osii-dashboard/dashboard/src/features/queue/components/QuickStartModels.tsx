import { useState } from "react";
import {
  Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress,
  MenuItem, Paper, Stack, TextField, Typography,
} from "@mui/material";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiJson } from "../../../api/client";
import { listModelProviders } from "../../../api/queue";
import { EndpointFields } from "../../models/components/EndpointFields";
import type { ModelOption } from "../../models/components/ModelPicker";
import { suggestedConnectionName } from "../../models/connectionName";

export type ModelRole = "embedding" | "language";
type Verification = { state: "ready" | "failed" | "needs_connection" | "needs_test"; models: string[]; bundled: boolean; detail?: string | null };
export type QuickStart = { ready: boolean } & Record<ModelRole, Verification>;
const labels = { embedding: "Embedding model", language: "Language model" };
const statusLabels = { ready: "Ready", failed: "Test failed", needs_test: "Test needed", needs_connection: "Connection needed" };

export function getQuickStart() {
  return apiJson<QuickStart>("/api/intake/quick-start");
}

function ConnectModel({ role, onClose, onSaved }: { role: ModelRole; onClose: () => void; onSaved: (value: QuickStart) => void }) {
  const providers = useQuery({ queryKey: ["admin", "model-providers"], queryFn: listModelProviders });
  const [providerId, setProviderId] = useState("");
  const [protocol, setProtocol] = useState<"openai" | "ollama">("openai");
  const [endpoint, setEndpoint] = useState("");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const provider = providers.data?.providers.find(item => item.id === providerId);
  const address = (provider?.base_url ?? endpoint).trim().replace(/\/$/, "");
  const type = provider?.type ?? protocol;
  const capability = role === "language" ? "chat" : "embedding";
  const discovery = useMutation({
    mutationFn: () => apiJson<{ models: ModelOption[] }>("/api/admin/model-providers/discover", {
      method: "POST", json: { provider_id: providerId || undefined, base_url: address, type, api_key: provider ? undefined : key },
    }),
    onSuccess: ({ models }) => {
      const matching = models.filter(item => !item.capabilities.length || item.capabilities.includes(capability));
      setModel(matching.length === 1 ? matching[0].id : "");
    },
  });
  const connect = useMutation({
    mutationFn: () => apiJson<QuickStart>("/api/intake/quick-start/connect", {
      method: "POST",
      json: { role, model, provider_id: providerId, protocol: type, endpoint: address, key: provider ? "" : key,
        display_name: suggestedConnectionName(address) },
    }),
    onSuccess: onSaved,
  });
  const reset = () => { setModel(""); discovery.reset(); connect.reset(); };
  const models = (discovery.data?.models ?? []).filter(item => !item.capabilities.length || item.capabilities.includes(capability));
  const busy = discovery.isPending || connect.isPending;
  const error = connect.error ?? discovery.error ?? providers.error;

  return (
    <Dialog open onClose={busy ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>Connect {labels[role].toLowerCase()}</DialogTitle>
      <DialogContent>
        <Stack component="fieldset" disabled={busy} spacing={1.5} sx={{ border: 0, m: 0, px: 0, pt: 1, minWidth: 0 }}>
          {providers.data?.providers.some(item => !item.implicit) && (
            <TextField select size="small" label="Connection" value={providerId}
              onChange={event => { setProviderId(event.target.value); reset(); }}>
              <MenuItem value="">New connection</MenuItem>
              {providers.data.providers.filter(item => !item.implicit).map(item => (
                <MenuItem key={item.id} value={item.id}>{item.display_name || item.id} · {item.base_url}</MenuItem>
              ))}
            </TextField>
          )}
          {!provider && <>
            <TextField select size="small" label="Endpoint type" value={protocol}
              onChange={event => {
                const value = event.target.value as "openai" | "ollama";
                setProtocol(value);
                setEndpoint(value === "ollama" ? "http://127.0.0.1:11434" : "");
                setKey("");
                reset();
              }}>
              <MenuItem value="openai">OpenAI-compatible</MenuItem>
              <MenuItem value="ollama">Ollama</MenuItem>
            </TextField>
            <EndpointFields baseUrl={endpoint} onBaseUrl={value => { setEndpoint(value); reset(); }}
              apiKey={key} onApiKey={value => { setKey(value); reset(); }} showCredential={protocol === "openai"}
              urlHelp={protocol === "ollama" ? "Enter the address of a running Ollama server." : "Enter the API base address, including /v1 where required."} />
          </>}
          <Button variant="outlined" disabled={busy || !address} onClick={() => discovery.mutate()} sx={{ alignSelf: "start" }}>
            {discovery.isPending ? "Finding models…" : "Find models"}
          </Button>
          {discovery.isSuccess && (models.length ? (
            <TextField select size="small" label={labels[role]} value={model} onChange={event => setModel(event.target.value)}>
              {models.map(option => <MenuItem key={option.id} value={option.id}>{option.name}</MenuItem>)}
            </TextField>
          ) : <Alert severity="info">No matching models were listed. Try another connection.</Alert>)}
          {error && <Alert severity="error">{error.message}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={busy || !model} onClick={() => connect.mutate()}>
          {connect.isPending ? "Testing…" : "Save and test"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function QuickStartModels({ data, loading, error, onUpdate, onRefresh }: {
  data?: QuickStart; loading: boolean; error?: Error | null;
  onUpdate: (value: QuickStart) => void; onRefresh: () => void;
}) {
  const [connecting, setConnecting] = useState<ModelRole | null>(null);
  const test = useMutation({
    mutationFn: (role: ModelRole) => apiJson<QuickStart>(`/api/intake/quick-start/check/${role}`, { method: "POST" }),
    onSuccess: onUpdate,
  });
  return (
    <Paper component="section" variant="outlined" aria-labelledby="connect-models" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Typography id="connect-models" component="h2" variant="h6" fontWeight={700}>1. Connect models</Typography>
        {loading && <LinearProgress aria-label="Checking saved models" />}
        {error && <Alert severity="error" action={<Button onClick={onRefresh}>Retry</Button>}>{error.message}</Alert>}
        {test.error && <Alert severity="error">{test.error.message}</Alert>}
        {data && (["embedding", "language"] as const).map(role => {
          const item = data[role];
          return (
            <Stack key={role} spacing={0.5} sx={{ py: 0.5 }}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography fontWeight={650}>{labels[role]}</Typography>
                <Chip size="small" label={statusLabels[item.state]} color={item.state === "ready" ? "success" : item.state === "failed" ? "warning" : "default"} />
                {!!item.models.length && <Typography variant="body2" color="text.secondary">{item.models.join(" · ")}</Typography>}
                {item.state !== "ready" && item.state !== "needs_connection" && (
                  <Button size="small" disabled={test.isPending} onClick={() => test.mutate(role)}>
                    {test.isPending && test.variables === role ? "Testing…" : `Test saved ${labels[role].toLowerCase()}`}
                  </Button>
                )}
                {!item.bundled && <Button size="small" disabled={test.isPending} onClick={() => setConnecting(role)}>
                  {item.state === "ready" ? "Change" : "Connect"} {labels[role].toLowerCase()}
                </Button>}
              </Stack>
              {item.state === "failed" && item.detail && <Alert severity="warning">{item.detail}</Alert>}
            </Stack>
          );
        })}
      </Stack>
      {connecting && <ConnectModel role={connecting} onClose={() => setConnecting(null)}
        onSaved={value => { setConnecting(null); onUpdate(value); }} />}
    </Paper>
  );
}
