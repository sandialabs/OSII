import { FormEvent, useState } from "react";
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip,
  Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel,
  LinearProgress, MenuItem, Paper, Stack, Switch, TextField, Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import {
  checkModelProvider, checkProcessorEndpoint, controlCapabilityService,
  createModelProvider, createProcessorEndpoint, deleteModelProviderCredential,
  getCapabilityServiceLogs, getOllamaPullStatus, getProcessorSettings,
  getSetupSummary, getExtractorRoutes, listModelProviders, listProcessorEndpoints, pullOllamaModel,
  saveExtractorRoutes, saveModelProviderCredential, saveProcessorSettings,
} from "../../../api/queue";
import type {
  CapabilityReadiness, ManagedCapabilityService, ModelProvider,
  ModelProviderHealth, ModelPullJob, OllamaRecommendation,
  ProcessorConfigProperty, ProcessorEndpoint, ExtractorRoute,
} from "../../../api/types";

const DEFAULT_EMBEDDING_MODEL = "all-minilm";
const DEFAULT_CHAT_MODEL = "llama3.2:1b";
const CAPABILITY_COPY = {
  extractor: ["Extractors", "Turn source files into grounded text and artifacts. File-type routing is configured below."],
  synthesizer: ["Synthesizers", "Create cited previews, summaries, and wiki text from extracted content."],
  embedder: ["Embedders", "Build vectors for semantic similarity. BM25 remains the normal no-model search baseline."],
  enricher: ["Enrichers", "Create keywords, entities, tables, graphs, and other reusable knowledge products."],
} as const;

function blankProvider(type: ModelProvider["type"]): ModelProvider {
  if (type === "openai") {
    return {
      id: "openai-compatible", type, base_url: "", enabled: true,
      priority: 10, embedding_model: "", synthesis_model: "",
      chat_model: "", credential_env: "OPENAI_API_KEY",
    };
  }
  if (type === "ollama") {
    return {
      id: "ollama-local", type, base_url: "http://127.0.0.1:11434", enabled: true,
      priority: 100, embedding_model: DEFAULT_EMBEDDING_MODEL,
      synthesis_model: DEFAULT_CHAT_MODEL, chat_model: DEFAULT_CHAT_MODEL, credential_env: "",
    };
  }
  return {
    id: "openai-compatible", type, base_url: "https://", enabled: true,
    priority: 50, embedding_model: "", synthesis_model: "", chat_model: "",
    credential_env: "OSII_MODEL_API_KEY",
  };
}

function statusColor(status: string): "success" | "default" | "error" | "info" {
  if (status === "running" || status === "external") return "success";
  if (status === "failed") return "error";
  if (status === "starting") return "info";
  return "default";
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
    fullWidth size="small" multiline={property.format === "textarea"}
    minRows={property.format === "textarea" ? 6 : undefined} label={label}
    type={numeric ? "number" : "text"} value={value ?? ""}
    inputProps={numeric ? { min: property.minimum, max: property.maximum, step: property.type === "integer" ? 1 : 0.1 } : undefined}
    onChange={(event) => onChange(numeric ? Number(event.target.value) : event.target.value)}
    helperText={property.description}
  />;
}

function ServiceRow({ service, busy, onAction, onLogs }: {
  service: ManagedCapabilityService;
  busy: boolean;
  onAction: (action: "start" | "stop" | "restart") => void;
  onLogs?: () => void;
}) {
  const label = service.status === "external" ? "Running externally" : service.status.replace(/_/g, " ");
  return <Stack spacing={0.75} sx={{ py: 0.75 }}>
    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
      <Stack spacing={0.25}>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="body2" fontWeight={700}>{service.display_name}</Typography>
          <Chip size="small" color={statusColor(service.status)} label={label} />
        </Stack>
        <Typography variant="caption" color="text.secondary">{service.description}</Typography>
        {service.prerequisite ? <Typography variant="caption" color="text.secondary">{service.prerequisite}</Typography> : null}
      </Stack>
      <Stack direction="row" spacing={0.75} alignItems="center">
        {service.can_start ? <Button size="small" variant="contained" disabled={busy} onClick={() => onAction("start")}>Start</Button> : null}
        {service.can_restart ? <Button size="small" variant="outlined" disabled={busy} onClick={() => onAction("restart")}>Restart</Button> : null}
        {service.can_stop ? <Button size="small" variant="text" disabled={busy} onClick={() => onAction("stop")}>Stop</Button> : null}
        {onLogs ? <Button size="small" variant="text" onClick={onLogs}>Logs</Button> : null}
      </Stack>
    </Stack>
  </Stack>;
}

export function ProcessorsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const setup = useQuery({ queryKey: ["admin", "setup"], queryFn: getSetupSummary, refetchInterval: 5000 });
  const providerData = useQuery({ queryKey: ["admin", "model-providers"], queryFn: listModelProviders });
  const processors = useQuery({ queryKey: ["admin", "processors"], queryFn: listProcessorEndpoints });
  const settings = useQuery({ queryKey: ["admin", "processor-settings"], queryFn: getProcessorSettings });
  const extractorRoutes = useQuery({ queryKey: ["admin", "extractor-routes"], queryFn: getExtractorRoutes });

  const [message, setMessage] = useState<string | null>(null);
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [providerForm, setProviderForm] = useState<ModelProvider>(blankProvider("openai"));
  const [apiKey, setApiKey] = useState("");
  const [providerHealth, setProviderHealth] = useState<Record<string, ModelProviderHealth>>({});
  const [savingConnection, setSavingConnection] = useState(false);
  const [serviceBusy, setServiceBusy] = useState<string | null>(null);
  const [serviceLogs, setServiceLogs] = useState<{ title: string; lines: string[] } | null>(null);
  const [pullJobs, setPullJobs] = useState<Record<string, ModelPullJob>>({});
  const [editingCapability, setEditingCapability] = useState<string | null>(null);
  const [capabilityDraft, setCapabilityDraft] = useState<Record<string, unknown>>({});
  const [routeDraft, setRouteDraft] = useState<ExtractorRoute[] | null>(null);
  const [savingRoutes, setSavingRoutes] = useState(false);
  const [processorForm, setProcessorForm] = useState<Omit<ProcessorEndpoint, "id"> & { id: string }>({
    id: "", display_name: "", kind: "extractor", base_url: "http://", enabled: true,
  });

  const refreshSetup = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "setup"] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "model-providers"] }),
      queryClient.invalidateQueries({ queryKey: ["intake", "readiness"] }),
    ]);
  };

  const openNewConnection = (type: ModelProvider["type"]) => {
    setProviderForm(blankProvider(type));
    setApiKey("");
    setConnectionOpen(true);
  };
  const openExistingConnection = (provider: ModelProvider) => {
    setProviderForm(provider);
    setApiKey("");
    setConnectionOpen(true);
  };

  const saveConnection = async (event: FormEvent) => {
    event.preventDefault();
    setSavingConnection(true);
    try {
      await createModelProvider(providerForm);
      if (apiKey) await saveModelProviderCredential(providerForm.id, apiKey);
      const health = await checkModelProvider(providerForm.id);
      setProviderHealth((current) => ({ ...current, [providerForm.id]: health }));
      const embeddingTest = health.capabilities?.embedding;
      setMessage(!health.ok
        ? `${providerForm.id} was saved, but the connection check failed: ${health.detail ?? "unavailable"}`
        : embeddingTest?.configured && !embeddingTest.ok
          ? `${providerForm.id} is connected, but its selected embedding model is not usable: ${embeddingTest.detail}`
          : embeddingTest?.ok
            ? `${providerForm.id} is connected; embedding model ${embeddingTest.model} returned ${embeddingTest.dimensions} dimensions.`
            : `${providerForm.id} is connected.`);
      setApiKey("");
      await refreshSetup();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save the connection.");
    } finally {
      setSavingConnection(false);
    }
  };

  const checkConnection = async (provider: ModelProvider) => {
    try {
      const health = await checkModelProvider(provider.id);
      setProviderHealth((current) => ({ ...current, [provider.id]: health }));
      const embeddingTest = health.capabilities?.embedding;
      setMessage(!health.ok
        ? `${provider.id}: ${health.detail ?? "unavailable"}`
        : embeddingTest?.configured && !embeddingTest.ok
          ? `${provider.id} is connected, but embeddings failed: ${embeddingTest.detail}`
          : embeddingTest?.ok
            ? `${provider.id}: embedding model ${embeddingTest.model} is ready (${embeddingTest.dimensions} dimensions).`
            : `${provider.id} is connected.`);
      await refreshSetup();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Connection check failed.");
    }
  };

  const forgetCredential = async (provider: ModelProvider) => {
    try {
      await deleteModelProviderCredential(provider.id);
      setMessage(`${provider.id}: saved API key removed.`);
      await refreshSetup();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not remove the saved key.");
    }
  };

  const runServiceAction = async (service: ManagedCapabilityService, action: "start" | "stop" | "restart") => {
    setServiceBusy(service.id);
    try {
      await controlCapabilityService(service.id, action);
      setMessage(`${service.display_name}: ${action} completed.`);
      await refreshSetup();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `${service.display_name}: action failed.`);
    } finally {
      setServiceBusy(null);
    }
  };

  const showLogs = async (service: ManagedCapabilityService) => {
    try {
      const result = await getCapabilityServiceLogs(service.id);
      setServiceLogs({ title: service.display_name, lines: result.lines });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load service logs.");
    }
  };

  const installModel = async (provider: ModelProvider, recommendation: OllamaRecommendation) => {
    const key = `${provider.id}:${recommendation.model}`;
    try {
      let job = await pullOllamaModel(provider.id, recommendation.model);
      setPullJobs((current) => ({ ...current, [key]: job }));
      while (["queued", "running"].includes(job.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        job = await getOllamaPullStatus(provider.id, job.job_id);
        setPullJobs((current) => ({ ...current, [key]: job }));
      }
      if (job.status === "error") throw new Error(job.detail || "Ollama could not download the model.");
      setMessage(`${recommendation.display_name} is installed.`);
      await checkConnection(provider);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Model download failed.");
    }
  };

  const addProcessor = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createProcessorEndpoint(processorForm);
      setProcessorForm({ id: "", display_name: "", kind: "extractor", base_url: "http://", enabled: true });
      setMessage("Custom processing service added.");
      await queryClient.invalidateQueries({ queryKey: ["admin", "processors"] });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add the service.");
    }
  };

  const schemaFor = (item: CapabilityReadiness) => item.config_schema ?? item.descriptor?.config_schema;
  const editCapability = (item: CapabilityReadiness) => {
    const saved = settings.data?.settings[item.id] ?? {};
    const properties = schemaFor(item)?.properties ?? {};
    setCapabilityDraft(Object.fromEntries(Object.entries(properties).flatMap(([name, property]) => (
      saved[name] !== undefined || property.default !== undefined ? [[name, saved[name] ?? property.default]] : []
    ))));
    setEditingCapability(item.id);
  };
  const saveCapability = async (item: CapabilityReadiness) => {
    await saveProcessorSettings(item.id, capabilityDraft);
    setEditingCapability(null);
    setMessage(`${item.display_name}: settings saved.`);
    await queryClient.invalidateQueries({ queryKey: ["admin", "processor-settings"] });
  };

  const currentRoutes = routeDraft ?? (extractorRoutes.data?.routes ?? []).map((route) => ({
    ...route,
    fallbacks: route.fallbacks ?? [],
  }));
  const updateRoute = (index: number, update: Partial<ExtractorRoute>) => {
    setRouteDraft(currentRoutes.map((route, routeIndex) => (
      routeIndex === index ? { ...route, ...update } : route
    )));
  };
  const addRoute = () => {
    const defaultExtractor = data?.methods.extractor.id || capabilityMethods("extractor")[0]?.id || "native_text";
    const next = [...currentRoutes];
    const catchAllIndex = next.findIndex((route) => route.extensions.includes("*"));
    const newRoute: ExtractorRoute = {
      name: `file-type-${next.length + 1}`,
      extractor: defaultExtractor,
      fallbacks: [],
      extensions: [".ext"],
    };
    next.splice(catchAllIndex < 0 ? next.length : catchAllIndex, 0, newRoute);
    setRouteDraft(next);
  };
  const persistRoutes = async () => {
    setSavingRoutes(true);
    try {
      const result = await saveExtractorRoutes(currentRoutes);
      if (!result.ok) throw new Error(result.errors?.join(" ") || "Extractor routes were not saved.");
      setRouteDraft(null);
      setMessage(result.warnings?.length
        ? `Extractor routes saved. ${result.warnings.join(" ")}`
        : "Extractor routes and fallback order saved.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "extractor-routes"] }),
        queryClient.invalidateQueries({ queryKey: ["intake"] }),
      ]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save extractor routes.");
    } finally {
      setSavingRoutes(false);
    }
  };

  const data = setup.data;
  const discoveredModels = providerHealth[providerForm.id]?.models ?? [];

  const capabilityMethods = (kind: keyof typeof CAPABILITY_COPY): CapabilityReadiness[] => {
    if (!data) return [];
    const group = kind === "extractor" ? data.readiness.extractors
      : kind === "synthesizer" ? data.readiness.synthesizers
        : kind === "embedder" ? data.readiness.embedders
          : data.readiness.enrichers;
    return group
      .filter((item, index, items) => items.findIndex((candidate) => candidate.id === item.id) === index)
      .filter((item) => !["firstN", "recursive"].includes(item.id));
  };

  const renderCapabilityCard = (kind: keyof typeof CAPABILITY_COPY) => {
    const [title, explanation] = CAPABILITY_COPY[kind];
    const selected = data?.methods[kind];
    const methods = capabilityMethods(kind);
    return <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.25}>
      <Stack spacing={0.25}>
        <Typography variant="h6" fontWeight={700}>{title}</Typography>
        <Typography variant="body2" color="text.secondary">{explanation}</Typography>
      </Stack>
      <Divider />
      {methods.map((item) => {
        const schema = schemaFor(item);
        const isSelected = kind === "extractor"
          ? currentRoutes.some((route) => [route.extractor, ...route.fallbacks].some(
            (id) => id === item.id || item.aliases?.includes(id),
          ))
          : selected?.id === item.id || item.aliases?.includes(selected?.id ?? "");
        return <Box key={item.id} sx={{ py: 0.5 }}><Stack spacing={0.6}>
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2" fontWeight={700}>{item.display_name}</Typography>
            {isSelected ? <Chip size="small" color="primary" label={kind === "extractor" ? "In routing" : "Default"} /> : null}
            <Chip size="small" color={item.available ? "success" : "default"} label={item.available ? "Available" : "Unavailable"} />
          </Stack>
          <Typography variant="caption" color="text.secondary">{item.description}</Typography>
          {!item.available ? <Typography variant="caption" color="text.secondary">{item.detail}</Typography> : null}
          {Object.keys(schema?.properties ?? {}).length ? <Button size="small" sx={{ alignSelf: "flex-start", px: 0 }} onClick={() => editingCapability === item.id ? setEditingCapability(null) : editCapability(item)}>{editingCapability === item.id ? "Hide settings" : "Settings"}</Button> : null}
          {editingCapability === item.id ? <Stack spacing={1}>{Object.entries(schema?.properties ?? {}).map(([name, property]) => <ConfigInput key={name} name={name} property={property} value={capabilityDraft[name]} onChange={(value) => setCapabilityDraft((current) => ({ ...current, [name]: value }))} />)}<Button variant="contained" size="small" onClick={() => void saveCapability(item)} sx={{ alignSelf: "flex-start" }}>Save settings</Button></Stack> : null}
          <Box component="details"><Typography component="summary" variant="caption" sx={{ cursor: "pointer" }}>Technical identity</Typography><Typography variant="caption" component="div"><code>{item.id}</code>{item.base_url ? <> · <code>{item.base_url}</code></> : null}</Typography></Box>
        </Stack></Box>;
      })}
      {!methods.length ? <Typography variant="body2" color="text.secondary">Checking methods…</Typography> : null}
    </Stack></Paper>;
  };

  return <Stack spacing={2.5}>
    <Stack spacing={0.5}>
      <Typography variant="h5" fontWeight={750}>Setup</Typography>
      <Typography color="text.secondary">Choose and inspect OSII&apos;s extractors, synthesizers, embedders, and enrichers in one place.</Typography>
    </Stack>

    {message ? <Alert severity={/failed|could not|error/i.test(message) ? "error" : "info"} onClose={() => setMessage(null)}>{message}</Alert> : null}
    {setup.isError ? <Alert severity="error"><strong>OSII&apos;s backend is not responding.</strong> Keep the development launcher running and refresh this page.</Alert> : null}

    <Paper variant="outlined" sx={{ p: 2, borderColor: data?.overall_status === "action_required" ? "error.main" : "success.main" }}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1.5} alignItems={{ md: "center" }}>
        <Stack spacing={0.25}>
          <Typography variant="h6" fontWeight={750}>{data?.headline ?? "Checking OSII…"}</Typography>
          <Typography variant="body2" color="text.secondary">
            {data?.ai_ready ? "The configured processing pipeline and model provider are available." : "Local processing works now. Add a model connection only when you want semantic search or generated answers."}
          </Typography>
        </Stack>
        <Button variant="contained" onClick={() => navigate("/intake")} disabled={!data?.extraction_ready}>Continue to Intake</Button>
      </Stack>
    </Paper>

    <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.25}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1} alignItems={{ md: "center" }}>
        <Stack spacing={0.2}><Typography fontWeight={700}>Model connections</Typography><Typography variant="body2" color="text.secondary">A connection can supply synthesizer and embedder methods; it is not itself a processing step.</Typography></Stack>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap><Button variant="contained" onClick={() => openNewConnection("openai")}>Add OpenAI-compatible</Button><Button variant="outlined" onClick={() => openNewConnection("ollama")}>Use Ollama</Button></Stack>
      </Stack>
      {(data?.providers ?? []).filter((provider) => provider.enabled).map((provider) => <Stack key={provider.id} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1} alignItems={{ sm: "center" }}><Stack><Typography variant="body2" fontWeight={700}>{provider.type === "ollama" ? "Ollama" : "OpenAI-compatible"} · {provider.id}</Typography><Typography variant="caption" color="text.secondary">{provider.embedding_model ? `Embedding: ${provider.embedding_model}` : "Embedding: not selected"} · {provider.synthesis_model ? `Synthesis: ${provider.synthesis_model}` : "Synthesis: not selected"}</Typography></Stack><Stack direction="row" spacing={1}><Button size="small" onClick={() => openExistingConnection(provider)}>Configure</Button><Button size="small" onClick={() => void checkConnection(provider)}>Test</Button></Stack></Stack>)}
      <Typography variant="caption" color="text.secondary">Without a model connection, OSII still supports extraction, enrichment, source-excerpt synthesis, and BM25 search.</Typography>
    </Stack></Paper>

    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
      {renderCapabilityCard("extractor")}
      {renderCapabilityCard("synthesizer")}
      {renderCapabilityCard("embedder")}
      {renderCapabilityCard("enricher")}
    </Box>

    <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1} alignItems={{ md: "center" }}>
        <Stack spacing={0.25}><Typography variant="h6" fontWeight={700}>Extraction routing</Typography><Typography variant="body2" color="text.secondary">For each file type, OSII tries the primary extractor first, then each fallback from left to right. Intake uses these saved rules automatically.</Typography></Stack>
        <Stack direction="row" spacing={1}><Button variant="outlined" onClick={addRoute}>Add file-type rule</Button><Button variant="contained" disabled={!routeDraft || savingRoutes} onClick={() => void persistRoutes()}>{savingRoutes ? "Saving…" : "Save routes"}</Button></Stack>
      </Stack>
      {extractorRoutes.isLoading ? <LinearProgress /> : null}
      {currentRoutes.map((route, index) => {
        const availableIds = capabilityMethods("extractor").map((item) => item.id);
        const choices = Array.from(new Set([route.extractor, ...route.fallbacks, ...availableIds]));
        return <Paper key={`${route.name}-${index}`} variant="outlined" sx={{ p: 1.5 }}><Stack spacing={1}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }} flexWrap="wrap" useFlexGap>
            <TextField size="small" label="File extensions" value={route.extensions.join(", ")} onChange={(event) => updateRoute(index, { extensions: event.target.value.split(",").map((value) => value.trim().toLowerCase()).filter(Boolean) })} helperText="Comma-separated, or * for everything else" sx={{ minWidth: 250 }} />
            <TextField select size="small" label="Primary extractor" value={route.extractor} onChange={(event) => updateRoute(index, { extractor: event.target.value, fallbacks: route.fallbacks.filter((item) => item !== event.target.value) })} sx={{ minWidth: 230 }}>{choices.map((id) => <MenuItem key={id} value={id}>{capabilityMethods("extractor").find((item) => item.id === id || item.aliases?.includes(id))?.display_name ?? id}</MenuItem>)}</TextField>
            <Typography aria-hidden color="text.secondary" fontSize="1.4rem">→</Typography>
            <TextField select size="small" label="First fallback" value={route.fallbacks[0] ?? ""} onChange={(event) => updateRoute(index, { fallbacks: event.target.value ? [event.target.value, ...route.fallbacks.slice(1).filter((id) => id !== event.target.value)] : [] })} sx={{ minWidth: 220 }}><MenuItem value="">No fallback</MenuItem>{choices.filter((id) => id !== route.extractor).map((id) => <MenuItem key={id} value={id}>{capabilityMethods("extractor").find((item) => item.id === id || item.aliases?.includes(id))?.display_name ?? id}</MenuItem>)}</TextField>
            <Typography aria-hidden color="text.secondary" fontSize="1.4rem">→</Typography>
            <TextField select size="small" label="Second fallback" disabled={!route.fallbacks[0]} value={route.fallbacks[1] ?? ""} onChange={(event) => updateRoute(index, { fallbacks: event.target.value ? [route.fallbacks[0], event.target.value, ...route.fallbacks.slice(2).filter((id) => id !== event.target.value)] : route.fallbacks.slice(0, 1) })} sx={{ minWidth: 220 }}><MenuItem value="">No second fallback</MenuItem>{choices.filter((id) => id !== route.extractor && id !== route.fallbacks[0]).map((id) => <MenuItem key={id} value={id}>{capabilityMethods("extractor").find((item) => item.id === id || item.aliases?.includes(id))?.display_name ?? id}</MenuItem>)}</TextField>
          </Stack>
          <Stack direction="row" spacing={0.75} alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap><Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap><Chip size="small" label={route.name} />{[route.extractor, ...route.fallbacks].map((id, chainIndex) => <Stack key={`${id}-${chainIndex}`} direction="row" spacing={0.75} alignItems="center">{chainIndex ? <Typography color="text.secondary">→</Typography> : null}<Chip size="small" color={capabilityMethods("extractor").find((item) => item.id === id || item.aliases?.includes(id))?.available ? "success" : "default"} variant="outlined" label={capabilityMethods("extractor").find((item) => item.id === id || item.aliases?.includes(id))?.display_name ?? id} /></Stack>)}</Stack><Button size="small" color="error" onClick={() => setRouteDraft(currentRoutes.filter((_, routeIndex) => routeIndex !== index))}>Remove rule</Button></Stack>
        </Stack></Paper>;
      })}
      {!currentRoutes.length && !extractorRoutes.isLoading ? <Alert severity="warning">No extraction routes are configured.</Alert> : null}
    </Stack></Paper>

    <Paper variant="outlined"><Accordion disableGutters elevation={0}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}><Stack><Typography fontWeight={700}>Advanced &amp; diagnostics</Typography><Typography variant="caption" color="text.secondary">Service controls, additional connections, custom processors, endpoints, and logs.</Typography></Stack></AccordionSummary>
      <AccordionDetails><Stack spacing={2}>
        <Accordion variant="outlined" disableGutters><AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography fontWeight={700}>Local capability services</Typography></AccordionSummary><AccordionDetails><Stack divider={<Divider flexItem />}>
          {(data?.services ?? []).map((service) => <ServiceRow key={service.id} service={service} busy={serviceBusy === service.id} onAction={(action) => void runServiceAction(service, action)} onLogs={() => void showLogs(service)} />)}
          {!data?.service_control_available ? <Alert severity="info">Lifecycle controls are available with <code>make dev</code> or <code>.\scripts\osii.ps1 dev</code>. This deployment reports health only.</Alert> : null}
        </Stack></AccordionDetails></Accordion>

        <Accordion variant="outlined" disableGutters><AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography fontWeight={700}>AI connections</Typography></AccordionSummary><AccordionDetails><Stack spacing={1.25}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}><Button variant="outlined" onClick={() => openNewConnection("openai")}>Add OpenAI-compatible</Button><Button variant="outlined" onClick={() => openNewConnection("ollama")}>Add Ollama</Button></Stack>
          {(data?.providers ?? []).map((provider) => <Paper key={provider.id} variant="outlined" sx={{ p: 1.5 }}><Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}><Stack><Typography variant="body2" fontWeight={700}>{provider.id}</Typography><Typography variant="caption" color="text.secondary">{provider.base_url} · priority {provider.priority} · {provider.enabled ? "enabled" : "disabled"}</Typography></Stack><Stack direction="row" spacing={1}><Button size="small" onClick={() => openExistingConnection(provider)}>Edit</Button><Button size="small" onClick={() => void checkConnection(provider)}>Test</Button>{provider.credential_present && provider.credential_source === "repo_env" ? <Button size="small" color="error" onClick={() => void forgetCredential(provider)}>Forget key</Button> : null}</Stack></Stack></Paper>)}
        </Stack></AccordionDetails></Accordion>

        <Accordion variant="outlined" disableGutters><AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography fontWeight={700}>Custom Processor API services</Typography></AccordionSummary><AccordionDetails><Stack spacing={1.5}>
          <Typography variant="body2" color="text.secondary">Connect an SME&apos;s extractor, synthesizer, embedder, or enricher. Enter its base address; OSII discovers its descriptor and settings.</Typography>
          <Box component="form" onSubmit={(event) => void addProcessor(event)}><Stack spacing={1}><Stack direction={{ xs: "column", md: "row" }} spacing={1}><TextField size="small" label="ID" required value={processorForm.id} onChange={(event) => setProcessorForm({ ...processorForm, id: event.target.value })} /><TextField size="small" label="Display name" required fullWidth value={processorForm.display_name} onChange={(event) => setProcessorForm({ ...processorForm, display_name: event.target.value })} /><TextField size="small" select label="Kind" value={processorForm.kind} onChange={(event) => setProcessorForm({ ...processorForm, kind: event.target.value as ProcessorEndpoint["kind"] })}>{["extractor", "synthesizer", "embedder", "enricher"].map((kind) => <MenuItem key={kind} value={kind}>{kind}</MenuItem>)}</TextField></Stack><TextField size="small" label="Base URL" required value={processorForm.base_url} onChange={(event) => setProcessorForm({ ...processorForm, base_url: event.target.value })} /><Button type="submit" variant="contained" sx={{ alignSelf: "flex-start" }}>Add service</Button></Stack></Box>
          {(processors.data?.processors ?? []).map((processor) => <Stack key={processor.id} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}><Stack><Typography variant="body2" fontWeight={700}>{processor.display_name}</Typography><Typography variant="caption" color="text.secondary">{processor.kind} · {processor.base_url}</Typography></Stack><Stack direction="row" spacing={1}><Button size="small" onClick={() => void checkProcessorEndpoint(processor.id, false).then((result) => setMessage(`${processor.display_name}: ${result.ok ? "healthy" : result.detail}`))}>Health</Button><Button size="small" variant="outlined" onClick={() => void checkProcessorEndpoint(processor.id, true).then((result) => setMessage(`${processor.display_name}: ${result.ok ? "test passed" : result.detail}`))}>Test</Button></Stack></Stack>)}
        </Stack></AccordionDetails></Accordion>
      </Stack></AccordionDetails>
    </Accordion></Paper>

    <Dialog open={connectionOpen} onClose={() => setConnectionOpen(false)} fullWidth maxWidth="sm"><Box component="form" onSubmit={(event) => void saveConnection(event)}>
      <DialogTitle>Configure model connection</DialogTitle><DialogContent><Stack spacing={1.5} sx={{ pt: 0.5 }}>
        <TextField select label="Connection" value={providerForm.type} onChange={(event) => setProviderForm(blankProvider(event.target.value as ModelProvider["type"]))}><MenuItem value="ollama">Ollama on this computer</MenuItem><MenuItem value="openai">OpenAI-compatible endpoint</MenuItem></TextField>
        <TextField label="Endpoint URL" required value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} helperText={providerForm.type === "ollama" ? "Ollama is installed and started separately. Use its local address here." : "Use the OpenAI-compatible /v1 base address."} />
        {providerForm.type !== "ollama" ? <TextField type="password" label={providerForm.credential_present ? "Replace saved API key (optional)" : "API key"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} helperText={providerForm.credential_source === "environment" ? "Managed by the process environment; it cannot be replaced here." : "Saved as plaintext in the repository-root .env, which Git ignores."} disabled={providerForm.credential_source === "environment"} /> : <Alert severity="info" icon={false}>Install and start Ollama yourself. OSII can inspect installed models and download the approved starters; use the Ollama CLI for other models and advanced options.</Alert>}
        <TextField label="Language model" value={providerForm.chat_model} onChange={(event) => setProviderForm({ ...providerForm, chat_model: event.target.value, synthesis_model: event.target.value })} helperText="Used for chat, summaries, and wiki generation." inputProps={{ list: "osii-model-options" }} />
        <TextField label="Embedding model (optional)" value={providerForm.embedding_model} onChange={(event) => setProviderForm({ ...providerForm, embedding_model: event.target.value })} helperText="Used for semantic similarity. Leave blank to use BM25 only." inputProps={{ list: "osii-model-options" }} />
        <datalist id="osii-model-options">{discoveredModels.map((model) => <option key={model} value={model} />)}</datalist>
        {providerHealth[providerForm.id] ? <Alert severity={!providerHealth[providerForm.id].ok || (providerHealth[providerForm.id].capabilities?.embedding?.configured && !providerHealth[providerForm.id].capabilities?.embedding?.ok) ? "error" : "success"}>
          {!providerHealth[providerForm.id].ok
            ? providerHealth[providerForm.id].detail
            : providerHealth[providerForm.id].capabilities?.embedding?.configured
              ? providerHealth[providerForm.id].capabilities?.embedding?.detail
              : `Connected. Found ${providerHealth[providerForm.id].models.length} model(s). Select an embedding model to validate embeddings.`}
        </Alert> : null}
        {providerForm.type === "ollama" ? <Stack spacing={1}><Typography variant="body2" fontWeight={700}>Small starter models</Typography>{(providerData.data?.ollama_recommendations ?? []).map((recommendation) => {
          const job = pullJobs[`${providerForm.id}:${recommendation.model}`];
          const active = job?.status === "queued" || job?.status === "running";
          const progress = job?.total ? Math.min(100, job.completed / job.total * 100) : undefined;
          return <Paper key={recommendation.model} variant="outlined" sx={{ p: 1.25 }}><Stack spacing={0.5}><Stack direction="row" justifyContent="space-between" spacing={1}><Stack><Typography variant="body2" fontWeight={700}>{recommendation.display_name}</Typography><Typography variant="caption" color="text.secondary">{recommendation.model} · {recommendation.size_label} · {recommendation.publisher}</Typography></Stack><Button size="small" variant="outlined" disabled={active} onClick={() => void installModel(providerForm, recommendation)}>{active ? "Downloading…" : "Download"}</Button></Stack>{active ? <LinearProgress variant={progress === undefined ? "indeterminate" : "determinate"} value={progress} /> : null}{job?.status === "error" ? <Typography variant="caption" color="error">{job.detail}</Typography> : null}</Stack></Paper>;
        })}</Stack> : null}
      </Stack></DialogContent><DialogActions><Button onClick={() => setConnectionOpen(false)}>Close</Button><Button type="submit" variant="contained" disabled={savingConnection}>{savingConnection ? "Saving and checking…" : "Save and check connection"}</Button></DialogActions>
    </Box></Dialog>

    <Dialog open={Boolean(serviceLogs)} onClose={() => setServiceLogs(null)} fullWidth maxWidth="md"><DialogTitle>{serviceLogs?.title} logs</DialogTitle><DialogContent><Box component="pre" sx={{ bgcolor: "grey.950", color: "grey.100", p: 1.5, borderRadius: 1, maxHeight: 420, overflow: "auto", whiteSpace: "pre-wrap", fontSize: "0.75rem" }}>{serviceLogs?.lines.join("\n") || "No recent output."}</Box></DialogContent><DialogActions><Button onClick={() => setServiceLogs(null)}>Close</Button></DialogActions></Dialog>
  </Stack>;
}
