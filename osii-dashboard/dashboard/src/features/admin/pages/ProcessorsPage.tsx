import { FormEvent, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Chip, Divider, FormControlLabel, LinearProgress, MenuItem, Paper, Stack, Switch, Tab, Tabs, TextField, Typography } from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { checkModelProvider, checkProcessorEndpoint, createModelProvider, createProcessorEndpoint, getIntakeReadiness, getOllamaPullStatus, getProcessorSettings, listModelProviders, listProcessorEndpoints, pullOllamaModel, saveProcessorSettings } from "../../../api/queue";
import type { CapabilityReadiness, ModelProvider, ModelProviderHealth, ModelPullJob, OllamaRecommendation, ProcessorConfigProperty, ProcessorEndpoint } from "../../../api/types";
import { ServiceStartGuide } from "../components/ServiceStartGuide";

const DEFAULT_EMBEDDING_MODEL = "all-minilm";
const DEFAULT_CHAT_MODEL = "llama3.2:1b";
const DEFAULT_SHIRTY_MODEL = "meta-llama/Llama-3.1-8B-Instruct";
const DEFAULT_SHIRTY_URL = "https://shirty.sandia.gov/api/v1";

type ProviderModelSelection = Pick<ModelProvider, "embedding_model" | "synthesis_model" | "chat_model">;

function modelMatches(installed: string, requested: string) {
  return installed === requested || installed === `${requested}:latest` || requested === `${installed}:latest`;
}

function formatBytes(value?: number | null) {
  if (!value) return "size unavailable";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.round(value / 1024 ** 2)} MB`;
}

function modelSelection(provider: ModelProvider): ProviderModelSelection {
  return {
    embedding_model: provider.embedding_model,
    synthesis_model: provider.synthesis_model,
    chat_model: provider.chat_model,
  };
}

function selectableModelNames(provider: ModelProvider, health: ModelProviderHealth) {
  return [...new Set([
    ...health.models,
    ...health.model_details.map((model) => model.name),
    provider.embedding_model,
    provider.synthesis_model,
    provider.chat_model,
  ].filter(Boolean))].sort((left, right) => left.localeCompare(right));
}

const LOCAL_CAPABILITY_GROUPS = [
  {
    key: "extractors" as const,
    title: "Extraction — read text from files",
    description: "Choose the actual program that reads each source file. OCR is separate from reading text already stored in a PDF.",
    defaultKey: "extractor" as const,
  },
  {
    key: "synthesizers" as const,
    title: "Synthesis — make cited previews or summaries",
    description: "A source-excerpt preview copies existing text; an Ollama, Shirty, or OpenAI model can generate a new grounded summary.",
    defaultKey: "synthesizer" as const,
  },
  {
    key: "embedders" as const,
    title: "Embedding — build vectors for similarity search",
    description: "Lexical hashing matches shared words. Ollama or another embedding model is required for semantic similarity. BM25 search works without either.",
    defaultKey: "embedder" as const,
  },
  {
    key: "enrichers" as const,
    title: "Enrichment — create additional knowledge products",
    description: "Build tables, phrase keywords, entity lists, graphs, or wiki Markdown from text that has already been extracted.",
    defaultKey: "enricher" as const,
  },
];

function uniqueCapabilities(items: CapabilityReadiness[]) {
  return items.filter(
    (item, index) => items.findIndex((candidate) => candidate.id === item.id) === index,
  );
}

function isSelectedDefault(item: CapabilityReadiness, selected: string) {
  return item.id === selected || item.aliases?.includes(selected);
}

function localRuntimeLabel(item: CapabilityReadiness) {
  const concreteLabels: Record<string, string> = {
    "local.native-text": "Python service on port 8092 · started by make dev · reads existing text, not scanned-page images",
    "local.extractive-preview": "Python service on port 8093 · started by make dev · copies cited excerpts without an AI model",
    "local.hashing": "Python service on port 8085 · started by make dev · token and word-pair hashing, not semantic understanding",
    "local.stats-keywords": "Python service on port 8094 · started by make dev · deterministic counts and frequent terms",
    stats_keywords: "Python enrichment inside OSII core · no model or additional service",
    noun_adjective_ngrams: "Python enrichment inside OSII core · lemmatized noun/adjective phrase counts · no model",
    entity_candidates: "Python enrichment inside OSII core · capitalized-name and acronym candidates · no model",
    osii_tesseract: "OpenCV + Tesseract OCR service on port 8080 · not started by make dev",
    tika: "Apache Tika server on port 9998 · not started by make dev",
    pdf_default: "External Nemotron vision-language-model service · not included with OSII",
    llm_wiki: "OSII enrichment that calls the selected model-backed synthesizer",
  };
  if (concreteLabels[item.id]) return concreteLabels[item.id];
  if (item.id.startsWith("ollama.")) {
    return "OSII's adapter runs on port 8095; the Ollama application and model run separately";
  }
  if (item.id.startsWith("corporate.shirty")) {
    return "OSII's adapter runs on port 8095 and calls the configured corporate Shirty endpoint";
  }
  if (item.bundled && item.base_url) return `Bundled Python service at ${item.base_url} · started by make dev`;
  if (item.base_url) return `Connected Processor API service at ${item.base_url}`;
  if (!item.available) return "Optional implementation · connect or start it separately";
  return "Python implementation inside OSII core";
}

function unavailableHelp(item: CapabilityReadiness) {
  if (item.id === "osii_tesseract") {
    return "Install Tesseract and confirm `tesseract --version`, then run `make dev-ocr-host` or `.\\scripts\\osii.ps1 dev-ocr-host`.";
  }
  if (item.id === "tika") {
    return "Apache Tika is optional. With Podman available, run `make dev-containers` or `.\\scripts\\osii.ps1 dev-containers`.";
  }
  if (item.id === "pdf_default") {
    return "Set NEMOTRON_BASE_URL to a running Nemotron/Banyan PDF parser endpoint.";
  }
  if (item.id.startsWith("ollama.")) {
    return "Install and start Ollama separately, then open AI models, check the connection, and download the model shown in this method's name.";
  }
  if (item.id === "llm_wiki") {
    return "Connect and test an Ollama, Shirty, or OpenAI-compatible synthesis model first.";
  }
  return "Start or connect this implementation, then retest tools.";
}

function capabilitySchema(item: CapabilityReadiness) {
  return item.config_schema ?? item.descriptor?.config_schema;
}

function defaultConfig(item: CapabilityReadiness, saved: Record<string, unknown>) {
  const properties = capabilitySchema(item)?.properties ?? {};
  return Object.fromEntries(
    Object.entries(properties).flatMap(([name, property]) => (
      saved[name] !== undefined || property.default !== undefined
        ? [[name, saved[name] ?? property.default]]
        : []
    )),
  );
}

function ConfigInput({ name, property, value, onChange }: {
  name: string;
  property: ProcessorConfigProperty;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const label = property.title ?? name.replace(/_/g, " ");
  if (property.type === "boolean") {
    return <FormControlLabel control={<Switch checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />} label={label} />;
  }
  if (property.enum?.length) {
    return <TextField select fullWidth size="small" label={label} value={value ?? ""} onChange={(event) => onChange(event.target.value)} helperText={property.description}>
      {property.enum.map((option) => <MenuItem key={String(option)} value={option}>{option}</MenuItem>)}
    </TextField>;
  }
  const numeric = property.type === "number" || property.type === "integer";
  return <TextField
    fullWidth
    size="small"
    multiline={property.format === "textarea"}
    minRows={property.format === "textarea" ? 7 : undefined}
    label={label}
    type={numeric ? "number" : "text"}
    value={value ?? ""}
    inputProps={numeric ? { min: property.minimum, max: property.maximum, step: property.type === "integer" ? 1 : 0.1 } : undefined}
    onChange={(event) => onChange(numeric ? Number(event.target.value) : event.target.value)}
    helperText={property.description}
  />;
}

export function ProcessorsPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const processors = useQuery({ queryKey: ["admin", "processors"], queryFn: listProcessorEndpoints });
  const providers = useQuery({ queryKey: ["admin", "model-providers"], queryFn: listModelProviders });
  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness });
  const processorSettings = useQuery({ queryKey: ["admin", "processor-settings"], queryFn: getProcessorSettings });
  const [form, setForm] = useState<Omit<ProcessorEndpoint, "id"> & { id: string }>({
    id: "", display_name: "", kind: "extractor", base_url: "http://", enabled: true,
  });
  const [message, setMessage] = useState<string | null>(null);
  const [providerForm, setProviderForm] = useState<ModelProvider>({
    id: "ollama-local", type: "ollama", base_url: "http://127.0.0.1:11434", enabled: true,
    priority: 100, embedding_model: DEFAULT_EMBEDDING_MODEL, synthesis_model: DEFAULT_CHAT_MODEL, chat_model: DEFAULT_CHAT_MODEL, credential_env: "",
  });
  const [providerHealth, setProviderHealth] = useState<Record<string, ModelProviderHealth>>({});
  const [providerModelDrafts, setProviderModelDrafts] = useState<Record<string, ProviderModelSelection>>({});
  const [checkingProviderId, setCheckingProviderId] = useState<string | null>(null);
  const [savingProviderId, setSavingProviderId] = useState<string | null>(null);
  const [pullJobs, setPullJobs] = useState<Record<string, ModelPullJob>>({});
  const [section, setSection] = useState<"overview" | "models" | "capabilities" | "endpoints">("overview");
  const [showProviderForm, setShowProviderForm] = useState(false);
  const [editingCapability, setEditingCapability] = useState<string | null>(null);
  const [capabilityDraft, setCapabilityDraft] = useState<Record<string, unknown>>({});
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
      setShowProviderForm(false);
      await client.invalidateQueries({ queryKey: ["admin", "model-providers"] });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save model provider.");
    }
  };

  const probeProvider = async (provider: ModelProvider) => {
    setCheckingProviderId(provider.id);
    try {
      await loadProviderModels(provider, true);
    } finally {
      setCheckingProviderId(null);
    }
  };

  const changeProviderType = (type: ModelProvider["type"]) => {
    if (type === "shirty") {
      setProviderForm({
        ...providerForm,
        type,
        base_url: DEFAULT_SHIRTY_URL,
        embedding_model: "",
        synthesis_model: DEFAULT_SHIRTY_MODEL,
        chat_model: DEFAULT_SHIRTY_MODEL,
        credential_env: "SHIRTY_API_KEY",
      });
      return;
    }
    if (type === "ollama") {
      setProviderForm({
        ...providerForm,
        type,
        base_url: "http://127.0.0.1:11434",
        embedding_model: DEFAULT_EMBEDDING_MODEL,
        synthesis_model: DEFAULT_CHAT_MODEL,
        chat_model: DEFAULT_CHAT_MODEL,
        credential_env: "",
      });
      return;
    }
    setProviderForm({
      ...providerForm,
      type,
      embedding_model: "",
      synthesis_model: "",
      chat_model: "",
      credential_env: "OSII_MODEL_API_KEY",
    });
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

  const updateProviderModel = (provider: ModelProvider, field: keyof ProviderModelSelection, model: string) => {
    setProviderModelDrafts((current) => ({
      ...current,
      [provider.id]: {
        ...(current[provider.id] ?? modelSelection(provider)),
        [field]: model,
      },
    }));
  };

  const saveProviderModels = async (provider: ModelProvider) => {
    const selection = providerModelDrafts[provider.id] ?? modelSelection(provider);
    setSavingProviderId(provider.id);
    try {
      await createModelProvider({ ...provider, ...selection });
      setMessage(`${provider.id}: model selections saved. New embedding models require a separate compatible index.`);
      setProviderModelDrafts((current) => {
        const next = { ...current };
        delete next[provider.id];
        return next;
      });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["admin", "model-providers"] }),
        client.invalidateQueries({ queryKey: ["intake", "readiness"] }),
      ]);
      await loadProviderModels({ ...provider, ...selection });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save model selections.");
    } finally {
      setSavingProviderId(null);
    }
  };

  const editCapability = (item: CapabilityReadiness) => {
    setEditingCapability(item.id);
    setCapabilityDraft(defaultConfig(item, processorSettings.data?.settings[item.id] ?? {}));
  };

  const saveCapability = async (item: CapabilityReadiness) => {
    try {
      await saveProcessorSettings(item.id, capabilityDraft);
      setMessage(`${item.display_name}: default settings saved.`);
      setEditingCapability(null);
      await client.invalidateQueries({ queryKey: ["admin", "processor-settings"] });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save processor settings.");
    }
  };

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>Tools &amp; services</Typography>
        <Typography color="text.secondary">
          See what <code>make dev</code> already started, what each processing method actually does, and which optional programs you must install or connect yourself.
        </Typography>
      </Stack>
      {message ? <Alert severity={message.includes("failed") || message.includes("Could not") ? "error" : "info"}>{message}</Alert> : null}

      <Paper variant="outlined" sx={{ px: 1 }}>
        <Tabs value={section} onChange={(_, value) => setSection(value)} variant="scrollable" allowScrollButtonsMobile aria-label="Tool sections">
          <Tab value="overview" label="Start & status" />
          <Tab value="models" label="AI models" />
          <Tab value="capabilities" label="Processing methods" />
          <Tab value="endpoints" label="Custom services" />
        </Tabs>
      </Paper>

      {section === "overview" ? <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2.5}>
          <ServiceStartGuide readiness={readiness.data} />
          <Divider />
          <Typography variant="caption" color="text.secondary">
            OSII core validates and saves results from every processing method. Optional services compute results but never write the canonical <code>.osii</code> store directly.
          </Typography>
          <Button variant="outlined" onClick={() => navigate("/intake")} sx={{ alignSelf: "flex-start" }}>
            Continue to Intake
          </Button>
        </Stack>
      </Paper> : null}

      {section === "models" ? <Paper component="form" onSubmit={(event) => void addProvider(event)} variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography fontWeight={700}>AI model connections</Typography>
          <Typography variant="body2" color="text.secondary">Models are optional. OSII connects to Ollama, Shirty, or a generic OpenAI-compatible server through the small adapter that <code>make dev</code> started on port 8095.</Typography>
          <Alert severity="info">
            <strong>OSII does not manage the Ollama application.</strong> If you use Ollama, install and start it separately. <code>make dev</code> starts only OSII&apos;s HTTP adapter; the connection check below reports whether the configured Ollama URL is reachable.
          </Alert>
          <Button variant="outlined" onClick={() => setShowProviderForm((current) => !current)} sx={{ alignSelf: "flex-start" }}>
            {showProviderForm ? "Hide connection settings" : "Add or edit a model connection"}
          </Button>
          {showProviderForm ? <>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
            <TextField label="Provider ID" value={providerForm.id} onChange={(event) => setProviderForm({ ...providerForm, id: event.target.value })} />
            <TextField select label="Type" value={providerForm.type} onChange={(event) => changeProviderType(event.target.value as ModelProvider["type"])} sx={{ minWidth: 140 }}>
              {(["ollama", "openai", "shirty"] as const).map((type) => <MenuItem key={type} value={type}>{type}</MenuItem>)}
            </TextField>
            <TextField label="Base URL" fullWidth value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
            {providerForm.type !== "shirty" ? <TextField label="Embedding model" value={providerForm.embedding_model} onChange={(event) => setProviderForm({ ...providerForm, embedding_model: event.target.value })} /> : null}
            <TextField label="Synthesis model" value={providerForm.synthesis_model} onChange={(event) => setProviderForm({ ...providerForm, synthesis_model: event.target.value })} />
            <TextField label="Chat model" value={providerForm.chat_model} onChange={(event) => setProviderForm({ ...providerForm, chat_model: event.target.value })} />
            <TextField label="Credential env name" value={providerForm.credential_env} onChange={(event) => setProviderForm({ ...providerForm, credential_env: event.target.value })} helperText="Example: SHIRTY_API_KEY. Never paste the key." />
          </Stack>
          <FormControlLabel control={<Switch checked={providerForm.enabled} onChange={(event) => setProviderForm({ ...providerForm, enabled: event.target.checked })} />} label="Enable this provider" />
          {providerForm.type === "shirty" ? <Alert severity="info">Built-in Shirty support covers Textract, synthesis, and chat through the documented HTTP API. The published Shirty examples do not define a remote embedding endpoint, so select Ollama or another OpenAI-compatible provider for embeddings.</Alert> : <Alert severity="info">The first-run defaults are the US-origin <code>all-minilm</code> embedding model and Meta <code>llama3.2:1b</code> for chat and synthesis. Downloads are explicit and restricted by <code>OSII_OLLAMA_ALLOWED_MODELS</code>.</Alert>}
          <Button type="submit" variant="contained" sx={{ alignSelf: "flex-start" }}>Save provider</Button>
          </> : null}
          {(providers.data?.providers ?? []).map((provider) => (
            <Paper key={provider.id} variant="outlined" sx={{ p: 1.5 }}>
              <Stack spacing={1.25}>
                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                  <Stack>
                    <Stack direction="row" spacing={0.75} alignItems="center">
                      <Typography fontWeight={600}>{provider.type === "ollama" ? "Ollama on this computer" : provider.type === "shirty" ? "Corporate Shirty" : provider.id}</Typography>
                      <Chip size="small" label={provider.type} />
                    </Stack>
                    <Typography variant="caption" color="text.secondary">{provider.base_url} · credentials {provider.credential_required === false ? "not required" : provider.credential_present ? "present" : "not present"} · {provider.enabled ? "enabled" : "disabled"}</Typography>
                    {provider.type === "shirty" ? <Typography variant="caption" color="text.secondary">Built in: Textract, synthesis, and chat. Embedding remains a separate provider capability.</Typography> : null}
                  </Stack>
                  <Stack direction="row" spacing={1}><Button variant="outlined" onClick={() => { setProviderForm(provider); setShowProviderForm(true); }}>Edit</Button><Button variant="outlined" disabled={checkingProviderId === provider.id} onClick={() => void probeProvider(provider)}>{checkingProviderId === provider.id ? "Checking…" : "Check connection & models"}</Button></Stack>
                </Stack>
                {provider.type === "ollama" && providerHealth[provider.id]?.ok ? <Alert severity="success">Connected to Ollama. Found {providerHealth[provider.id].models.length} installed model{providerHealth[provider.id].models.length === 1 ? "" : "s"}.</Alert> : null}
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
                    {!providerHealth[provider.id].models.length ? <Typography variant="caption" color="text.secondary">Ollama is connected, but no models are installed.</Typography> : null}
                    {providerHealth[provider.id].models.length ? (
                      <Paper variant="outlined" sx={{ p: 1.25, mt: 0.5 }}>
                        <Stack spacing={1}>
                          <Stack spacing={0.25}>
                            <Typography variant="body2" fontWeight={700}>Use installed models in OSII</Typography>
                            <Typography variant="caption" color="text.secondary">
                              Select independently because a chat model may not support embeddings. OSII uses the exact Ollama model name shown here; changing the embedding model requires building a compatible index.
                            </Typography>
                          </Stack>
                          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                            {([
                              ["embedding_model", "Embedding model"],
                              ["synthesis_model", "Synthesis model"],
                              ["chat_model", "Chat model"],
                            ] as const).map(([field, label]) => {
                              const selection = providerModelDrafts[provider.id] ?? modelSelection(provider);
                              const installed = providerHealth[provider.id].models.some((name) => modelMatches(name, selection[field]));
                              return (
                                <TextField
                                  key={field}
                                  select
                                  fullWidth
                                  size="small"
                                  label={label}
                                  value={selection[field]}
                                  onChange={(event) => updateProviderModel(provider, field, event.target.value)}
                                  helperText={installed ? "Installed" : "Configured model is not installed"}
                                >
                                  {selectableModelNames(provider, providerHealth[provider.id]).map((name) => (
                                    <MenuItem key={name} value={name}>
                                      {name}{providerHealth[provider.id].models.some((installedName) => modelMatches(installedName, name)) ? "" : " (not installed)"}
                                    </MenuItem>
                                  ))}
                                </TextField>
                              );
                            })}
                          </Stack>
                          <Button
                            variant="contained"
                            disabled={savingProviderId === provider.id || !providerModelDrafts[provider.id]}
                            onClick={() => void saveProviderModels(provider)}
                            sx={{ alignSelf: "flex-start" }}
                          >
                            {savingProviderId === provider.id ? "Saving…" : "Save model selections"}
                          </Button>
                        </Stack>
                      </Paper>
                    ) : null}
                  </Stack>
                ) : null}
                {provider.type === "ollama" && providerHealth[provider.id] && !providerHealth[provider.id].ok ? <Alert severity="info"><strong>OSII could not reach Ollama at this URL.</strong> Ollama may be stopped, installed at another address, or not installed. Start the application or run <code>ollama serve</code>, verify the URL, and check again.</Alert> : null}
                {provider.type === "ollama" ? (
                  <Stack spacing={1}>
                    <Typography variant="body2" fontWeight={700}>Approved starter models</Typography>
                    <Typography variant="caption" color="text.secondary">These buttons cover OSII&apos;s small starter models. Use <code>ollama list</code> and <code>ollama pull &lt;model&gt;</code> in the CLI for other models allowed in your environment, then check the connection again.</Typography>
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
      </Paper> : null}

      {section === "capabilities" ? <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack spacing={0.5}>
            <Typography fontWeight={700}>Processing methods and defaults</Typography>
            <Typography variant="body2" color="text.secondary">
              Each card says what the implementation actually uses and produces. <strong>Default for Intake</strong> means OSII selects it automatically; it does not mean optional software is installed.
            </Typography>
          </Stack>
          {readiness.data ? <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
            {LOCAL_CAPABILITY_GROUPS.map((group) => {
              const items = uniqueCapabilities(readiness.data[group.key]);
              const selected = readiness.data.defaults[group.defaultKey];
              return (
                <Paper key={group.key} variant="outlined" sx={{ p: 1.75 }}>
                  <Stack spacing={1.25}>
                    <Stack spacing={0.25}>
                      <Typography variant="subtitle1" fontWeight={700}>{group.title}</Typography>
                      <Typography variant="caption" color="text.secondary">{group.description}</Typography>
                    </Stack>
                    <Divider />
                    {items.map((item) => (
                      <Stack key={item.id} spacing={0.5}>
                        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                          <Typography variant="body2" fontWeight={650}>{item.display_name}</Typography>
                          {isSelectedDefault(item, selected) ? <Chip size="small" color="primary" label="Default for Intake" /> : null}
                          <Chip size="small" color={item.available ? "success" : "warning"} label={item.available ? "Running and usable" : "Needs setup"} />
                        </Stack>
                        {item.description ? <Typography variant="body2">{item.description}</Typography> : null}
                        <Typography variant="caption" color="text.secondary">{localRuntimeLabel(item)}</Typography>
                        {!item.available ? <Alert severity="warning" sx={{ py: 0.25 }}>{unavailableHelp(item)}</Alert> : null}
                        <Box component="details" sx={{ color: "text.secondary" }}>
                          <Typography component="summary" variant="caption" sx={{ cursor: "pointer" }}>Technical details</Typography>
                          <Stack spacing={0.25} sx={{ mt: 0.5 }}>
                            <Typography variant="caption">Processor ID: <code>{item.id}</code></Typography>
                            {item.base_url ? <Typography variant="caption">Service URL: <code>{item.base_url}</code></Typography> : null}
                            <Typography variant="caption">Readiness check: {item.detail}</Typography>
                          </Stack>
                        </Box>
                        {Object.keys(capabilitySchema(item)?.properties ?? {}).length ? (
                          <Button size="small" variant="text" onClick={() => editingCapability === item.id ? setEditingCapability(null) : editCapability(item)} sx={{ alignSelf: "flex-start", px: 0 }}>
                            {editingCapability === item.id ? "Hide settings" : "View and edit settings"}
                          </Button>
                        ) : null}
                        {editingCapability === item.id ? <Paper variant="outlined" sx={{ p: 1.5, mt: 0.5 }}>
                          <Stack spacing={1.25}>
                            <Typography variant="body2" fontWeight={700}>{item.display_name} defaults</Typography>
                            {Object.entries(capabilitySchema(item)?.properties ?? {}).map(([name, property]) => (
                              <ConfigInput key={name} name={name} property={property} value={capabilityDraft[name]} onChange={(value) => setCapabilityDraft((current) => ({ ...current, [name]: value }))} />
                            ))}
                            <Alert severity="info">These are non-secret defaults stored in <code>.osii/state/processor_settings.json</code>. Per-run API values override them.</Alert>
                            <Stack direction="row" spacing={1}>
                              <Button variant="contained" onClick={() => void saveCapability(item)}>Save defaults</Button>
                              <Button variant="outlined" onClick={() => setEditingCapability(null)}>Cancel</Button>
                            </Stack>
                          </Stack>
                        </Paper> : null}
                      </Stack>
                    ))}
                    {!items.length ? <Alert severity="info">No implementation was discovered for this processing step.</Alert> : null}
                  </Stack>
                </Paper>
              );
            })}
          </Box> : <Typography variant="body2">Testing local services…</Typography>}
        </Stack>
      </Paper> : null}

      {section === "endpoints" ? <>
      <Paper component="form" onSubmit={(event) => void add(event)} variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>Connect a custom OSII processing service</Typography>
            <Typography variant="body2" color="text.secondary">
              Use this for an SME&apos;s custom extractor, synthesizer, embedder, or enricher. Start that service first; it must implement Processor API v1: <code>/health</code>, <code>/v1/descriptor</code>, and one operation endpoint for its kind.
            </Typography>
          </Stack>
          <Alert severity="info">
            <strong>Host development:</strong> use its localhost base URL, such as <code>http://127.0.0.1:8091</code>. <strong>Packaged containers:</strong> use its Compose service name, or <code>host.containers.internal</code> for a service running on the host. Add the base address only—never append <code>/health</code> or <code>/v1</code>.
          </Alert>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
            <TextField label="ID" required value={form.id} onChange={(event) => setForm({ ...form, id: event.target.value })} />
            <TextField label="Display name" required fullWidth value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} />
            <TextField select label="Kind" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as ProcessorEndpoint["kind"] })} sx={{ minWidth: 150 }}>
              {["extractor", "synthesizer", "embedder", "enricher"].map((kind) => <MenuItem key={kind} value={kind}>{kind}</MenuItem>)}
            </TextField>
          </Stack>
          <TextField label="Base URL" required fullWidth value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="http://127.0.0.1:8091" helperText="Base address only; OSII appends the health, descriptor, and operation paths." />
          <Button type="submit" variant="contained" sx={{ alignSelf: "flex-start" }}>Add custom service</Button>
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
      </> : null}
    </Stack>
  );
}
