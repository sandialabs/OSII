import { FormEvent, useState } from "react";
import { Alert, Button, Chip, Divider, FormControlLabel, MenuItem, Paper, Stack, Switch, TextField, Typography } from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { checkModelProvider, checkProcessorEndpoint, createModelProvider, createProcessorEndpoint, getIntakeReadiness, listModelProviders, listProcessorEndpoints } from "../../../api/queue";
import type { ModelProvider, ProcessorEndpoint } from "../../../api/types";

export function ProcessorsPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const processors = useQuery({ queryKey: ["admin", "processors"], queryFn: listProcessorEndpoints });
  const providers = useQuery({ queryKey: ["admin", "model-providers"], queryFn: listModelProviders });
  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness });
  const [form, setForm] = useState<Omit<ProcessorEndpoint, "id"> & { id: string }>({
    id: "", display_name: "", kind: "extractor", base_url: "http://", enabled: true,
  });
  const [message, setMessage] = useState<string | null>(null);
  const [providerForm, setProviderForm] = useState<ModelProvider>({
    id: "ollama-local", type: "ollama", base_url: "http://127.0.0.1:11434", enabled: false,
    priority: 100, embedding_model: "", synthesis_model: "", chat_model: "", credential_env: "",
  });

  const add = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createProcessorEndpoint(form);
      setMessage("Processor endpoint added.");
      setForm({ id: "", display_name: "", kind: "extractor", base_url: "http://", enabled: true });
      await client.invalidateQueries({ queryKey: ["admin", "processors"] });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add processor endpoint.");
    }
  };

  const check = async (processor: ProcessorEndpoint, test: boolean) => {
    try {
      const result = await checkProcessorEndpoint(processor.id, test);
      setMessage(`${processor.display_name}: ${result.ok ? "passed" : "failed"} — ${result.detail}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Processor check failed.");
    }
  };

  const addProvider = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createModelProvider(providerForm);
      setMessage("Model provider saved. Models remain unselected until you enter their exact installed names.");
      await client.invalidateQueries({ queryKey: ["admin", "model-providers"] });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save model provider.");
    }
  };

  const probeProvider = async (provider: ModelProvider) => {
    const result = await checkModelProvider(provider.id);
    const commands = result.pull_commands.length ? ` Missing models: ${result.pull_commands.join("; ")}` : "";
    setMessage(`${provider.id}: ${result.ok ? `connected; ${result.models.length} installed model(s)` : result.detail ?? "unavailable"}.${commands}`);
  };

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>Tools</Typography>
        <Typography color="text.secondary">
          Guaranteed local capabilities work offline. Model providers and domain Processor services are separate, optional connections.
        </Typography>
      </Stack>
      {message ? <Alert severity={message.includes("failed") || message.includes("Could not") ? "error" : "info"}>{message}</Alert> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.25}>
          <Typography fontWeight={700}>Guaranteed local capabilities</Typography>
          <Typography variant="body2">Native extraction, extractive previews and chat, hashing vectors, BM25 search, and statistics/keyword enrichment require no account, model download, or container.</Typography>
          <Alert severity="info">Hashing vectors are lexical—not semantic. Intake and BM25 search remain available when every optional provider is down.</Alert>
          <Divider />
          <Typography fontWeight={700}>How to connect a domain processor</Typography>
          <Typography variant="body2">
            1. Start the processor service and confirm that its base URL is reachable from the OSII API.
          </Typography>
          <Typography variant="body2">
            2. Add that base URL below. Do not include <code>/health</code> or <code>/v1</code> in the URL.
          </Typography>
          <Typography variant="body2">
            3. Select <strong>Health</strong> to check connectivity, then <strong>Test</strong> to validate its descriptor and operation contract.
          </Typography>
          <Typography variant="body2">
            4. Return to Intake and select <strong>Retest tools</strong>. The processor will then appear in readiness and routing choices supported by the core.
          </Typography>
          <Alert severity="info">
            With <code>make dev</code>, a service running on this computer normally uses a URL such as <code>http://127.0.0.1:8091</code>. From the packaged container stack, use its Compose service name or <code>host.containers.internal</code> when calling a service on the host.
          </Alert>
          <Typography variant="caption" color="text.secondary">
            Core commits validated results from every Processor API kind. Processor services never write the `.osii` store directly.
          </Typography>
          <Button variant="outlined" onClick={() => navigate("/intake")} sx={{ alignSelf: "flex-start" }}>
            Return to Intake
          </Button>
        </Stack>
      </Paper>

      <Paper component="form" onSubmit={(event) => void addProvider(event)} variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography fontWeight={700}>Model providers</Typography>
          <Typography variant="body2" color="text.secondary">Ollama, Shirty, and generic OpenAI-compatible servers are adapted by a thin HTTP bridge. They are not custom OSII Processors. OSII stores only this non-secret configuration.</Typography>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
            <TextField label="Provider ID" value={providerForm.id} onChange={(event) => setProviderForm({ ...providerForm, id: event.target.value })} />
            <TextField select label="Type" value={providerForm.type} onChange={(event) => setProviderForm({ ...providerForm, type: event.target.value as ModelProvider["type"] })} sx={{ minWidth: 140 }}>
              {(["ollama", "openai", "shirty"] as const).map((type) => <MenuItem key={type} value={type}>{type}</MenuItem>)}
            </TextField>
            <TextField label="Base URL" fullWidth value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
            <TextField label="Embedding model" value={providerForm.embedding_model} onChange={(event) => setProviderForm({ ...providerForm, embedding_model: event.target.value })} />
            <TextField label="Synthesis model" value={providerForm.synthesis_model} onChange={(event) => setProviderForm({ ...providerForm, synthesis_model: event.target.value })} />
            <TextField label="Chat model" value={providerForm.chat_model} onChange={(event) => setProviderForm({ ...providerForm, chat_model: event.target.value })} />
            <TextField label="Credential env name" value={providerForm.credential_env} onChange={(event) => setProviderForm({ ...providerForm, credential_env: event.target.value })} helperText="Example: SHIRTY_API_KEY. Never paste the key." />
          </Stack>
          <FormControlLabel control={<Switch checked={providerForm.enabled} onChange={(event) => setProviderForm({ ...providerForm, enabled: event.target.checked })} />} label="Enable this provider" />
          <Alert severity="warning">Model names are explicit. OSII never chooses or downloads an Ollama model. If a model is missing, Health gives a copy-paste <code>ollama pull</code> command.</Alert>
          <Button type="submit" variant="contained" sx={{ alignSelf: "flex-start" }}>Save provider</Button>
          {(providers.data?.providers ?? []).map((provider) => (
            <Stack key={provider.id} direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
              <Stack><Typography fontWeight={600}>{provider.id} <Chip size="small" label={provider.type} /></Typography><Typography variant="caption" color="text.secondary">{provider.base_url} · credentials {provider.credential_present ? "present" : "not present"} · {provider.enabled ? "enabled" : "disabled"}</Typography></Stack>
              <Stack direction="row" spacing={1}><Button variant="outlined" onClick={() => setProviderForm(provider)}>Edit</Button><Button variant="outlined" onClick={() => void probeProvider(provider)}>Health & models</Button></Stack>
            </Stack>
          ))}
          <Divider />
          <Typography variant="body2" fontWeight={700}>Available vector indexes</Typography>
          {(readiness.data?.semantic_indexes ?? []).map((index) => <Typography key={index.index_id} variant="caption" color="text.secondary">{index.provider_id} · {index.model} · {index.dimensions ?? "?"} dimensions · {index.semantic ? "semantic" : "lexical hashing"} · {index.compatible ? "compatible" : "rebuild required"}</Typography>)}
          {readiness.data && !(readiness.data.semantic_indexes?.length) ? <Typography variant="caption" color="text.secondary">No provider/model-specific index has been built yet.</Typography> : null}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.25}>
          <Typography fontWeight={700}>Selected local Processor services</Typography>
          {readiness.data ? ([
            ...readiness.data.extractors,
            ...readiness.data.synthesizers,
            ...readiness.data.embedders,
            ...readiness.data.enrichers,
          ].filter((item, index, items) => item.bundled && items.findIndex((candidate) => candidate.id === item.id) === index).map((item) => (
            <Stack key={item.id} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
              <Stack>
                <Typography fontWeight={600}>{item.display_name}</Typography>
                <Typography variant="caption" color="text.secondary">{item.id} · {item.base_url ?? "in-process compatibility fallback"}</Typography>
              </Stack>
              <Chip size="small" color={item.available ? "success" : "error"} label={item.available ? item.detail : "Unavailable"} />
            </Stack>
          ))) : <Typography variant="body2">Testing local services…</Typography>}
        </Stack>
      </Paper>

      <Paper component="form" onSubmit={(event) => void add(event)} variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>Add an OSII Processor service</Typography>
            <Typography variant="body2" color="text.secondary">
              The service must implement OSII Processor API v1: <code>/health</code>, <code>/v1/descriptor</code>, and one operation endpoint for its kind.
            </Typography>
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
            <TextField label="ID" required value={form.id} onChange={(event) => setForm({ ...form, id: event.target.value })} />
            <TextField label="Display name" required fullWidth value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} />
            <TextField select label="Kind" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as ProcessorEndpoint["kind"] })} sx={{ minWidth: 150 }}>
              {["extractor", "synthesizer", "embedder", "enricher"].map((kind) => <MenuItem key={kind} value={kind}>{kind}</MenuItem>)}
            </TextField>
          </Stack>
          <TextField label="Base URL" required fullWidth value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="http://127.0.0.1:8091" helperText="Base address only; OSII appends the health, descriptor, and operation paths." />
          <Button type="submit" variant="contained" sx={{ alignSelf: "flex-start" }}>Add processor</Button>
        </Stack>
      </Paper>

      <Stack spacing={1.5}>
        {(processors.data?.processors ?? []).map((processor) => (
          <Paper key={processor.id} variant="outlined" sx={{ p: 2 }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} justifyContent="space-between">
              <Stack spacing={0.5}>
                <Stack direction="row" spacing={1} alignItems="center"><Typography fontWeight={700}>{processor.display_name}</Typography><Chip size="small" label={processor.kind} /></Stack>
                <Typography variant="body2" color="text.secondary">{processor.base_url}</Typography>
              </Stack>
              <Stack direction="row" spacing={1}><Button variant="outlined" onClick={() => void check(processor, false)}>Health</Button><Button variant="contained" onClick={() => void check(processor, true)}>Test</Button></Stack>
            </Stack>
          </Paper>
        ))}
        {!processors.isLoading && !(processors.data?.processors.length) ? <Alert severity="info">No external processors are registered.</Alert> : null}
      </Stack>
    </Stack>
  );
}
