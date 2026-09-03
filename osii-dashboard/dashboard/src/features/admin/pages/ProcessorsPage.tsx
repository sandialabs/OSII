import { FormEvent, useState } from "react";
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip,
  Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel,
  LinearProgress, MenuItem, Paper, Snackbar, Stack, Switch, TextField, Typography,
} from "@mui/material";
import type { AlertColor } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import TextSnippetOutlinedIcon from "@mui/icons-material/TextSnippetOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import ExtensionOutlinedIcon from "@mui/icons-material/ExtensionOutlined";
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
  synthesizer: ["Synthesizers", "Use a language model to create grounded summaries and wiki text."],
  embedder: ["Embedders", "Connect an embedding model for semantic search and related documents."],
  enricher: ["Enrichers", "Create keywords, entities, tables, graphs, and other reusable knowledge products."],
} as const;
const CAPABILITY_ICONS = {
  extractor: TextSnippetOutlinedIcon,
  synthesizer: AutoAwesomeOutlinedIcon,
  embedder: HubOutlinedIcon,
  enricher: ExtensionOutlinedIcon,
};
const BUNDLED_FALLBACKS = new Set(["native_text", "local.native-text", "local.extractive-preview", "local.hashing", "local.stats-keywords"]);

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

  const [notice, setNotice] = useState<{ text: string; severity: AlertColor; id: number } | null>(null);
  const notify = (text: string, severity: AlertColor = "success") => setNotice({ text, severity, id: Date.now() });
  const [expandedCapability, setExpandedCapability] = useState<keyof typeof CAPABILITY_COPY | false>(false);
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
      notify(!health.ok
        ? `${providerForm.id} was saved, but the connection check failed: ${health.detail ?? "unavailable"}`
        : embeddingTest?.configured && !embeddingTest.ok
          ? `${providerForm.id} is connected, but its selected embedding model is not usable: ${embeddingTest.detail}`
          : embeddingTest?.ok
            ? `${providerForm.id} is connected; embedding model ${embeddingTest.model} returned ${embeddingTest.dimensions} dimensions.`
            : `${providerForm.id} is connected.`, !health.ok || (embeddingTest?.configured && !embeddingTest.ok) ? "error" : "success");
      setApiKey("");
      await refreshSetup();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not save the connection.", "error");
    } finally {
      setSavingConnection(false);
    }
  };

  const checkConnection = async (provider: ModelProvider) => {
    notify(`${provider.id}: checking connection and selected models…`, "info");
    try {
      const health = await checkModelProvider(provider.id);
      setProviderHealth((current) => ({ ...current, [provider.id]: health }));
      const embeddingTest = health.capabilities?.embedding;
      notify(!health.ok
        ? `${provider.id}: ${health.detail ?? "unavailable"}`
        : embeddingTest?.configured && !embeddingTest.ok
          ? `${provider.id} is connected, but embeddings failed: ${embeddingTest.detail}`
          : embeddingTest?.ok
            ? `${provider.id}: embedding model ${embeddingTest.model} is ready (${embeddingTest.dimensions} dimensions).`
            : `${provider.id} is connected.`, !health.ok || (embeddingTest?.configured && !embeddingTest.ok) ? "error" : "success");
      await refreshSetup();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Connection check failed.", "error");
    }
  };

  const forgetCredential = async (provider: ModelProvider) => {
    try {
      await deleteModelProviderCredential(provider.id);
      notify(`${provider.id}: saved API key removed.`);
      await refreshSetup();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not remove the saved key.", "error");
    }
  };

  const runServiceAction = async (service: ManagedCapabilityService, action: "start" | "stop" | "restart") => {
    setServiceBusy(service.id);
    notify(`${service.display_name}: ${action} in progress…`, "info");
    try {
      const result = await controlCapabilityService(service.id, action);
      if (result.status === "failed") throw new Error(`${service.display_name}: ${result.detail || "service failed to start. Open Logs for details."}`);
      notify(`${service.display_name}: ${action} completed.`);
      await refreshSetup();
    } catch (error) {
      notify(error instanceof Error ? error.message : `${service.display_name}: action failed.`, "error");
    } finally {
      setServiceBusy(null);
    }
  };

  const showLogs = async (service: ManagedCapabilityService) => {
    try {
      const result = await getCapabilityServiceLogs(service.id);
      setServiceLogs({ title: service.display_name, lines: result.lines });
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not load service logs.", "error");
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
      notify(`${recommendation.display_name} is installed.`);
      await checkConnection(provider);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Model download failed.", "error");
    }
  };

  const addProcessor = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createProcessorEndpoint(processorForm);
      setProcessorForm({ id: "", display_name: "", kind: "extractor", base_url: "http://", enabled: true });
      notify("Custom processing service added.");
      await queryClient.invalidateQueries({ queryKey: ["admin", "processors"] });
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not add the service.", "error");
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
    try {
      await saveProcessorSettings(item.id, capabilityDraft);
      setEditingCapability(null);
      notify(`${item.display_name}: settings saved.`);
      await queryClient.invalidateQueries({ queryKey: ["admin", "processor-settings"] });
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not save processor settings.", "error");
    }
  };

  const testProcessor = async (processor: ProcessorEndpoint, runTest: boolean) => {
    notify(`${processor.display_name}: ${runTest ? "testing processor" : "checking health"}…`, "info");
    try {
      const result = await checkProcessorEndpoint(processor.id, runTest);
      notify(`${processor.display_name}: ${result.ok ? (runTest ? "test passed" : "healthy") : result.detail}`, result.ok ? "success" : "error");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not check the processor.", "error");
    }
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
      notify(result.warnings?.length
        ? `Extractor routes saved. ${result.warnings.join(" ")}`
        : "Extractor routes and fallback order saved.", result.warnings?.length ? "warning" : "success");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "extractor-routes"] }),
        queryClient.invalidateQueries({ queryKey: ["intake"] }),
      ]);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not save extractor routes.", "error");
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

  const renderExtractionRouting = () => (
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
  );

  const renderCapabilityDrawer = (kind: keyof typeof CAPABILITY_COPY) => {
    const [title, explanation] = CAPABILITY_COPY[kind];
    const selected = data?.methods[kind];
    const methods = capabilityMethods(kind);
    const Icon = CAPABILITY_ICONS[kind];
    const defaultLabel = !selected ? "Checking configured methods…"
      : kind === "extractor" ? `${currentRoutes.length} file-type rules · ${selected.display_name}`
        : kind === "embedder" && (!selected.available || selected.id === "bm25") ? "Connect an embedding model · BM25 fallback available"
          : `${BUNDLED_FALLBACKS.has(selected.id) ? "Fallback" : "Default"} · ${selected.display_name}${selected.model && !selected.display_name.includes(selected.model) ? ` · ${selected.model}` : ""}`;
    return <Accordion
      key={kind} disableGutters elevation={0}
      expanded={expandedCapability === kind}
      onChange={(_, expanded) => setExpandedCapability(expanded ? kind : false)}
      slotProps={{ transition: { unmountOnExit: true } }}
      sx={{
        border: "1px solid", borderColor: expandedCapability === kind ? "secondary.main" : "divider",
        borderRadius: "12px !important", overflow: "hidden", "&:before": { display: "none" },
      }}
    >
      <AccordionSummary
        id={`setup-${kind}-heading`} aria-controls={`setup-${kind}-content`}
        expandIcon={<ExpandMoreIcon />} sx={{ px: { xs: 1.5, sm: 2 }, minHeight: 80, "&:hover": { bgcolor: "rgba(0,95,114,0.025)" } }}
      >
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: "100%", minWidth: 0, pr: 1 }}>
          <Box sx={{ display: "grid", placeItems: "center", flexShrink: 0, width: 42, height: 42, borderRadius: 2, bgcolor: "rgba(102,206,227,0.15)", color: "secondary.main" }}><Icon /></Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography fontWeight={750}>{title}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>{defaultLabel}</Typography>
          </Box>
          <Chip variant="outlined" label={data ? `${methods.filter((item) => item.available).length} available` : "Checking…"} sx={{ display: { xs: "none", sm: "inline-flex" }, flexShrink: 0 }} />
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ px: { xs: 1.5, sm: 2.5 }, pb: 2.5 }}><Stack spacing={1.25}>
      <Typography variant="body2" color="text.secondary">{explanation}</Typography>
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
            {BUNDLED_FALLBACKS.has(item.id) ? <Chip size="small" variant="outlined" label="Bundled fallback" /> : null}
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
      {kind === "extractor" ? renderExtractionRouting() : null}
    </Stack></AccordionDetails></Accordion>;
  };

  // Render feedback inside the active dialog when present, so its focus trap
  // and screen-reader boundary include the notification and its Close button.
  const renderNotice = () => (
    <Snackbar
      key={notice?.id} open={Boolean(notice)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      autoHideDuration={notice?.severity === "success" ? 8000 : null}
      onClose={(_, reason) => { if (reason !== "clickaway") setNotice(null); }}
    >
      <Alert severity={notice?.severity ?? "info"} variant="filled" onClose={() => setNotice(null)} sx={{ width: "100%", maxWidth: 520, boxShadow: 4, overflowWrap: "anywhere" }}>
        {notice?.text}
      </Alert>
    </Snackbar>
  );

  return <Stack spacing={2.5}>
    <Stack spacing={0.5}>
      <Typography variant="h5" fontWeight={750}>Setup</Typography>
      <Typography color="text.secondary">Connect your AI models, then choose how OSII reads and works with your files.</Typography>
    </Stack>

    {!connectionOpen && !serviceLogs ? renderNotice() : null}
    {setup.isError ? <Alert severity="error"><strong>OSII&apos;s backend is not responding.</strong> Keep the development launcher running and refresh this page.</Alert> : null}

    <Paper variant="outlined" sx={{ p: { xs: 2, sm: 2.5 }, borderRadius: 2, background: "linear-gradient(115deg, rgba(102,206,227,0.16), rgba(255,255,255,0.9))", borderColor: data?.overall_status === "action_required" ? "error.main" : "rgba(0,95,114,0.18)" }}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1.5} alignItems={{ md: "center" }}>
        <Stack spacing={0.25}>
          <Typography variant="h6" fontWeight={750}>{data?.headline ?? "Checking OSII…"}</Typography>
          <Typography variant="body2" color="text.secondary">
            {data?.ai_ready ? "AI methods are available. Review the defaults below for your processing workflow." : "Connect a language model and an embedding model for the full OSII experience. Bundled fallbacks keep basic work moving while AI services are unavailable."}
          </Typography>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
          {data && !data.ai_ready ? <Button variant="contained" color="secondary" onClick={() => openNewConnection("openai")}>Connect AI</Button> : null}
          <Button variant={data?.ai_ready ? "contained" : "outlined"} color="secondary" onClick={() => navigate("/intake")} disabled={!data?.extraction_ready}>Continue to Intake</Button>
        </Stack>
      </Stack>
    </Paper>

    <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.25}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1} alignItems={{ md: "center" }}>
        <Stack spacing={0.2}><Typography fontWeight={700}>AI model connections</Typography><Typography variant="body2" color="text.secondary">Use a shared endpoint or Ollama on this computer for chat, synthesis, and semantic search.</Typography></Stack>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap><Button variant="contained" color="secondary" onClick={() => openNewConnection("openai")}>Add OpenAI-compatible</Button><Button variant="outlined" color="secondary" onClick={() => openNewConnection("ollama")}>Use Ollama</Button></Stack>
      </Stack>
      {(data?.providers ?? []).filter((provider) => provider.enabled).map((provider) => <Stack key={provider.id} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1} alignItems={{ sm: "center" }}><Stack><Typography variant="body2" fontWeight={700}>{provider.type === "ollama" ? "Ollama" : "OpenAI-compatible"} · {provider.id}</Typography><Typography variant="caption" color="text.secondary">{provider.embedding_model ? `Embedding: ${provider.embedding_model}` : "Embedding: not selected"} · {provider.synthesis_model ? `Synthesis: ${provider.synthesis_model}` : "Synthesis: not selected"}</Typography></Stack><Stack direction="row" spacing={1}><Button size="small" onClick={() => openExistingConnection(provider)}>Configure</Button><Button size="small" onClick={() => void checkConnection(provider)}>Test</Button></Stack></Stack>)}
    </Stack></Paper>

    <Stack spacing={1.25}>
      <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.08em" }}>Processing methods · open a drawer to configure</Typography>
      {renderCapabilityDrawer("extractor")}
      {renderCapabilityDrawer("synthesizer")}
      {renderCapabilityDrawer("embedder")}
      {renderCapabilityDrawer("enricher")}
    </Stack>


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
          {(processors.data?.processors ?? []).map((processor) => <Stack key={processor.id} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}><Stack><Typography variant="body2" fontWeight={700}>{processor.display_name}</Typography><Typography variant="caption" color="text.secondary">{processor.kind} · {processor.base_url}</Typography></Stack><Stack direction="row" spacing={1}><Button size="small" onClick={() => void testProcessor(processor, false)}>Health</Button><Button size="small" variant="outlined" onClick={() => void testProcessor(processor, true)}>Test</Button></Stack></Stack>)}
        </Stack></AccordionDetails></Accordion>
      </Stack></AccordionDetails>
    </Accordion></Paper>

    <Dialog open={connectionOpen} onClose={() => setConnectionOpen(false)} fullWidth maxWidth="sm"><Box component="form" onSubmit={(event) => void saveConnection(event)}>
      <DialogTitle>Configure model connection</DialogTitle><DialogContent>
      {connectionOpen && !serviceLogs ? renderNotice() : null}
      <Stack spacing={1.5} sx={{ pt: 0.5 }}>
        <TextField select label="Connection" value={providerForm.type} onChange={(event) => setProviderForm(blankProvider(event.target.value as ModelProvider["type"]))}><MenuItem value="ollama">Ollama on this computer</MenuItem><MenuItem value="openai">OpenAI-compatible endpoint</MenuItem></TextField>
        <TextField label="Endpoint URL" required value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} helperText={providerForm.type === "ollama" ? "Ollama is installed and started separately. Use its local address here." : "Use the OpenAI-compatible /v1 base address."} />
        {providerForm.type !== "ollama" ? <TextField type="password" label={providerForm.credential_present ? "Replace saved API key (optional)" : "API key"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} helperText={providerForm.credential_source === "environment" ? "Managed by the process environment; it cannot be replaced here." : "Saved as plaintext in the repository-root .env, which Git ignores."} disabled={providerForm.credential_source === "environment"} /> : <Alert severity="info" icon={false}>Install and start Ollama yourself. OSII can inspect installed models and download the approved starters; use the Ollama CLI for other models and advanced options.</Alert>}
        <TextField label="Language model" value={providerForm.chat_model} onChange={(event) => setProviderForm({ ...providerForm, chat_model: event.target.value, synthesis_model: event.target.value })} helperText="Used for chat, summaries, and wiki generation." inputProps={{ list: "osii-model-options" }} />
        <TextField label="Embedding model" value={providerForm.embedding_model} onChange={(event) => setProviderForm({ ...providerForm, embedding_model: event.target.value })} helperText="Powers semantic search. If this connection has no embedding model, configure one on another connection; BM25 is the keyword fallback." inputProps={{ list: "osii-model-options" }} />
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

    <Dialog open={Boolean(serviceLogs)} onClose={() => setServiceLogs(null)} fullWidth maxWidth="md"><DialogTitle>{serviceLogs?.title} logs</DialogTitle><DialogContent>{serviceLogs ? renderNotice() : null}<Box component="pre" sx={{ bgcolor: "grey.950", color: "grey.100", p: 1.5, borderRadius: 1, maxHeight: 420, overflow: "auto", whiteSpace: "pre-wrap", fontSize: "0.75rem" }}>{serviceLogs?.lines.join("\n") || "No recent output."}</Box></DialogContent><DialogActions><Button onClick={() => setServiceLogs(null)}>Close</Button></DialogActions></Dialog>
  </Stack>;
}
