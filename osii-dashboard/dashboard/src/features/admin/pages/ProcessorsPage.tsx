import { FormEvent, useEffect, useRef, useState } from "react";
import { Alert, Button, Chip, Divider, FormControlLabel, LinearProgress, MenuItem, Paper, Stack, Switch, TextField, Typography } from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { checkModelProvider, checkProcessorEndpoint, createModelProvider, createProcessorEndpoint, getIntakeReadiness, getOllamaPullStatus, listModelProviders, listProcessorEndpoints, pullOllamaModel } from "../../../api/queue";
import type { ModelProvider, ModelProviderHealth, ModelPullJob, OllamaRecommendation, ProcessorEndpoint } from "../../../api/types";

const DEFAULT_EMBEDDING_MODEL = "all-minilm";
const DEFAULT_CHAT_MODEL = "llama3.2:1b";

function modelMatches(installed: string, requested: string) {
  return installed === requested || installed === `${requested}:latest` || requested === `${installed}:latest`;
}

function formatBytes(value?: number | null) {
  if (!value) return "size unavailable";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.round(value / 1024 ** 2)} MB`;
}

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
    id: "ollama-local", type: "ollama", base_url: "http://127.0.0.1:11434", enabled: true,
    priority: 100, embedding_model: DEFAULT_EMBEDDING_MODEL, synthesis_model: DEFAULT_CHAT_MODEL, chat_model: DEFAULT_CHAT_MODEL, credential_env: "",
  });
  const [providerHealth, setProviderHealth] = useState<Record<string, ModelProviderHealth>>({});
  const [pullJobs, setPullJobs] = useState<Record<string, ModelPullJob>>({});
  const autoProbed = useRef(new Set<string>());

  const loadProviderModels = async (provider: ModelProvider, announce = false) => {
    try {
      const result = await checkModelProvider(provider.id);
      setProviderHealth((current) => ({ ...current, [provider.id]: result }));
      if (announce) {
        setMessage(`${provider.id}: ${result.ok ? `connected; ${result.models.length} installed model(s)` : result.detail ?? "unavailable"}.`);
      }
      return result;
    } catch (error) {
      if (announce) setMessage(error instanceof Error ? error.message : "Provider check failed.");
      return null;
    }
  };

  useEffect(() => {
    for (const provider of providers.data?.providers ?? []) {
      if (provider.type !== "ollama" || autoProbed.current.has(provider.id)) continue;
      autoProbed.current.add(provider.id);
      void loadProviderModels(provider);
    }
  }, [providers.data]);

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
      setMessage("Model provider saved. The highest-priority enabled provider supplies each configured capability.");
      await client.invalidateQueries({ queryKey: ["admin", "model-providers"] });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save model provider.");
    }
  };

  const probeProvider = async (provider: ModelProvider) => {
    await loadProviderModels(provider, true);
  };

  const installModel = async (provider: ModelProvider, recommendation: OllamaRecommendation) => {
    try {
      const jobKey = `${provider.id}:${recommendation.model}`;
      let job = await pullOllamaModel(provider.id, recommendation.model);
      setPullJobs((current) => ({ ...current, [jobKey]: job }));
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        job = await getOllamaPullStatus(provider.id, job.job_id);
        setPullJobs((current) => ({ ...current, [jobKey]: job }));
      }
      if (job.status === "error") throw new Error(job.detail || `Could not download ${recommendation.model}`);
      setMessage(`${recommendation.display_name} installed through Ollama.`);
      await loadProviderModels(provider);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Model download failed.");
    }
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
          <Typography variant="body2" color="text.secondary">Ollama, Shirty, and generic OpenAI-compatible servers are adapted by a thin HTTP bridge. Ollama itself and its model files remain separate from OSII, so this module can be disabled when a reliable endpoint is available.</Typography>
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
          <Alert severity="info">The first-run defaults are the US-origin <code>all-minilm</code> embedding model and Meta <code>llama3.2:1b</code> for chat and synthesis. Downloads are explicit and restricted by <code>OSII_OLLAMA_ALLOWED_MODELS</code>.</Alert>
          <Button type="submit" variant="contained" sx={{ alignSelf: "flex-start" }}>Save provider</Button>
          {(providers.data?.providers ?? []).map((provider) => (
            <Paper key={provider.id} variant="outlined" sx={{ p: 1.5 }}>
              <Stack spacing={1.25}>
                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                  <Stack>
                    <Stack direction="row" spacing={0.75} alignItems="center">
                      <Typography fontWeight={600}>{provider.id}</Typography>
                      <Chip size="small" label={provider.type} />
                    </Stack>
                    <Typography variant="caption" color="text.secondary">{provider.base_url} · credentials {provider.credential_required === false ? "not required" : provider.credential_present ? "present" : "not present"} · {provider.enabled ? "enabled" : "disabled"}</Typography>
                  </Stack>
                  <Stack direction="row" spacing={1}><Button variant="outlined" onClick={() => setProviderForm(provider)}>Edit</Button><Button variant="outlined" onClick={() => void probeProvider(provider)}>Refresh models</Button></Stack>
                </Stack>
                {provider.type === "ollama" && providerHealth[provider.id]?.ok ? (
                  <Stack spacing={0.75}>
                    <Typography variant="body2" fontWeight={700}>Installed Ollama models</Typography>
                    {providerHealth[provider.id].model_details.map((model) => {
                      const embeddingSelected = modelMatches(model.name, provider.embedding_model);
                      const chatSelected = modelMatches(model.name, provider.chat_model) || modelMatches(model.name, provider.synthesis_model);
                      return (
                        <Stack key={model.name} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                          <Stack direction="row" spacing={0.5} alignItems="center"><Typography variant="body2">{model.name}</Typography>{embeddingSelected ? <Chip size="small" label="embedding selected" /> : null}{chatSelected ? <Chip size="small" label="chat selected" /> : null}</Stack>
                          <Typography variant="caption" color="text.secondary">{[formatBytes(model.size), model.parameter_size, model.quantization_level].filter(Boolean).join(" · ")}</Typography>
                        </Stack>
                      );
                    })}
                    {!providerHealth[provider.id].model_details.length ? <Typography variant="caption" color="text.secondary">Ollama is connected, but no models are installed.</Typography> : null}
                  </Stack>
                ) : null}
                {provider.type === "ollama" && providerHealth[provider.id] && !providerHealth[provider.id].ok ? <Alert severity="warning">Ollama is not reachable at this URL. Start Ollama, then refresh this pane.</Alert> : null}
                {provider.type === "ollama" ? (
                  <Stack spacing={1}>
                    <Typography variant="body2" fontWeight={700}>Approved starter models</Typography>
                    {(providers.data?.ollama_recommendations ?? []).map((recommendation) => {
                      const installed = (providerHealth[provider.id]?.models ?? []).some((name) => modelMatches(name, recommendation.model));
                      const job = pullJobs[`${provider.id}:${recommendation.model}`];
                      const progress = job?.total ? Math.min(100, (job.completed / job.total) * 100) : undefined;
                      const active = job?.status === "queued" || job?.status === "running";
                      return (
                        <Paper key={recommendation.model} variant="outlined" sx={{ p: 1.25 }}>
                          <Stack spacing={0.75}>
                            <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                              <Stack>
                                <Stack direction="row" spacing={0.75} alignItems="center">
                                  <Typography variant="body2" fontWeight={700}>{recommendation.display_name}</Typography>
                                  <Chip size="small" label={recommendation.capability} />
                                </Stack>
                                <Typography variant="caption" color="text.secondary">{recommendation.model} · {recommendation.publisher} · {recommendation.size_label}</Typography>
                                <Typography variant="caption" color="text.secondary">{recommendation.description}</Typography>
                              </Stack>
                              <Button disabled={installed || active || !providerHealth[provider.id]?.ok} variant={installed ? "outlined" : "contained"} onClick={() => void installModel(provider, recommendation)}>
                                {installed ? "Installed" : active ? "Downloading…" : `Download ${recommendation.size_label}`}
                              </Button>
                            </Stack>
                            {active ? <Stack spacing={0.25}><LinearProgress variant={progress === undefined ? "indeterminate" : "determinate"} value={progress} /><Typography variant="caption" color="text.secondary">{job.status_text}{progress === undefined ? "" : ` · ${Math.round(progress)}%`}</Typography></Stack> : null}
                          </Stack>
                        </Paper>
                      );
                    })}
                  </Stack>
                ) : null}
              </Stack>
            </Paper>
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
