import { ProcessorConfigInput as ConfigInput } from "../../queue/components/ProcessorConfigInput";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip,
  Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel,
  IconButton, LinearProgress, MenuItem, Paper, Snackbar, Stack, Switch, TextField, Tooltip, Typography,
} from "@mui/material";
import type { AlertColor } from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import TextSnippetOutlinedIcon from "@mui/icons-material/TextSnippetOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import ExtensionOutlinedIcon from "@mui/icons-material/ExtensionOutlined";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  checkModelProvider, checkProcessorEndpoint, controlCapabilityService,
  createModelProvider, createProcessorEndpoint, deleteModelProvider, deleteModelProviderCredential, deleteProcessorEndpoint,
  getCapabilityServiceLogs, getOllamaPullStatus, getProcessorSettings,
  getSetupSummary, getExtractorRoutes, listModelProviders, listProcessorEndpoints, pullOllamaModel,
  saveExtractorRoutes, saveModelProviderCredential, saveProcessorSettings, updateProcessorEndpoint,
} from "../../../api/queue";
import type {
  CapabilityReadiness, ManagedCapabilityService, ModelProvider,
  ModelProviderHealth, ModelPullJob, OllamaRecommendation,
  ProcessorConfigProperty, ProcessorEndpoint, ExtractorRoute,
} from "../../../api/types";
import { WorkflowProgress } from "../../../components/discovery/WorkflowProgress";
import type { WorkflowStepId } from "../../../domain/workflow";

import { apiJson } from "../../../api/client";
import { ModelPicker, type ModelOption } from "../../models/components/ModelPicker";
import { EndpointFields } from "../../models/components/EndpointFields";

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
      default_chat: false, default_embedding: false,
    };
  }
  return {
    id: "ollama-local", type, base_url: "http://127.0.0.1:11434", enabled: true,
    priority: 100, embedding_model: DEFAULT_EMBEDDING_MODEL,
    synthesis_model: DEFAULT_CHAT_MODEL, chat_model: DEFAULT_CHAT_MODEL, credential_env: "",
    default_chat: false, default_embedding: false,
  };
}

function statusColor(status: string): "success" | "default" | "error" | "info" {
  if (status === "running" || status === "external") return "success";
  if (status === "failed") return "error";
  if (status === "starting") return "info";
  return "default";
}

function modelNameMatches(installed: string, requested: string): boolean {
  return installed === requested
    || installed === `${requested}:latest`
    || requested === `${installed}:latest`;
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

function ConnectionEndpointStatus({ provider, generation }: { provider: ModelProvider; generation?: number }) {
  const health = useQuery({
    queryKey: ["admin", "endpoint-health", provider.id, provider.type, provider.base_url, generation],
    queryFn: ({ signal }) => apiJson<{ models: ModelOption[] }>("/api/admin/model-providers/discover", {
      method: "POST", signal, json: { provider_id: provider.id, type: provider.type, base_url: provider.base_url },
    }),
    staleTime: 30_000, refetchInterval: 60_000, retry: false,
  });
  const label = health.isError ? "Endpoint unavailable" : health.data ? "Endpoint reachable" : "Checking endpoint…";
  const detail = health.isError ? (health.error instanceof Error ? health.error.message : "Connection check failed")
    : health.data ? `Model list checked ${new Date(health.dataUpdatedAt).toLocaleTimeString()}. Generation not tested.` : "Checking the endpoint’s model list.";
  return <Tooltip title={detail}><Chip size="small" tabIndex={0} aria-label={`${provider.id}: ${label}`} variant="outlined" color={health.isError ? "error" : health.data ? "success" : "default"} label={label} /></Tooltip>;
}

export function ProcessorsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedStep = searchParams.get("step");
  const focusedWorkflowStep = useRef<string | null>(null);
  const setup = useQuery({ queryKey: ["admin", "setup"], queryFn: getSetupSummary, refetchInterval: 5000 });
  const providerData = useQuery({ queryKey: ["admin", "model-providers"], queryFn: listModelProviders, refetchInterval: 5000 });
  const processors = useQuery({ queryKey: ["admin", "processors"], queryFn: listProcessorEndpoints, refetchInterval: 5000 });
  const settings = useQuery({ queryKey: ["admin", "processor-settings"], queryFn: getProcessorSettings });
  const extractorRoutes = useQuery({ queryKey: ["admin", "extractor-routes"], queryFn: getExtractorRoutes });

  const [notice, setNotice] = useState<{ text: string; severity: AlertColor; id: number } | null>(null);
  const notify = (text: string, severity: AlertColor = "success") => setNotice({ text, severity, id: Date.now() });
  const [expandedCapability, setExpandedCapability] = useState<keyof typeof CAPABILITY_COPY | false>(false);
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [providerForm, setProviderForm] = useState<ModelProvider>(blankProvider("openai"));
  const [apiKey, setApiKey] = useState("");
  const [catalogQueried, setCatalogQueried] = useState(false);
  const [catalogModels, setCatalogModels] = useState<ModelOption[]>([]);
  const [discoveringModels, setDiscoveringModels] = useState(false);
  const discoveryVersion = useRef(0);
  useEffect(() => { discoveryVersion.current += 1; setCatalogModels([]); setCatalogQueried(false); }, [connectionOpen, providerForm.base_url, providerForm.type, apiKey]);
  const findModels = async () => {
    const version = discoveryVersion.current;
    setDiscoveringModels(true);
    try {
      const result = await apiJson<{ models: ModelOption[] }>("/api/admin/model-providers/discover", {
        method: "POST", json: { type: providerForm.type, base_url: providerForm.base_url, api_key: apiKey, provider_id: editingProviderId || "" },
      });
      if (version === discoveryVersion.current) {
        setCatalogModels(result.models); setCatalogQueried(true);
        notify(`Found ${result.models.length} available models. Choose one below; nothing has been saved or invoked.`);
      }
    } catch (error) { if (version === discoveryVersion.current) notify((error as Error).message, "error"); }
    finally { setDiscoveringModels(false); }
  };
  const [providerHealth, setProviderHealth] = useState<Record<string, ModelProviderHealth>>({});
  const [savingConnection, setSavingConnection] = useState(false);
  const [serviceBusy, setServiceBusy] = useState<string | null>(null);
  const [serviceLogs, setServiceLogs] = useState<{ title: string; lines: string[] } | null>(null);
  const [pullJobs, setPullJobs] = useState<Record<string, ModelPullJob>>({});
  const [editingCapability, setEditingCapability] = useState<string | null>(null);
  const [capabilityDraft, setCapabilityDraft] = useState<Record<string, unknown>>({});
  const [routeDraft, setRouteDraft] = useState<ExtractorRoute[] | null>(null);
  const [tikaEndpoint, setTikaEndpoint] = useState<string | null>(null);
  const [sourceHelp, setSourceHelp] = useState<CapabilityReadiness | null>(null);
  const [routingHelp, setRoutingHelp] = useState(false);
  const [savingRoutes, setSavingRoutes] = useState(false);
  const [processorForm, setProcessorForm] = useState({
    base_url: "http://", model_connection: "",
  });

  useEffect(() => {
    if (!connectionOpen || providerForm.type !== "ollama" || !providerForm.id) return;
    let cancelled = false;
    void checkModelProvider(providerForm.id).then((health) => {
      if (!cancelled) {
        setProviderHealth((current) => ({ ...current, [providerForm.id]: health }));
      }
    }).catch(() => {
      // The dialog's normal connection check reports details after Save.
    });
    return () => { cancelled = true; };
  }, [connectionOpen, providerForm.id, providerForm.type]);

  const refreshSetup = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "setup"] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "model-providers"] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "endpoint-health"] }),
      queryClient.invalidateQueries({ queryKey: ["intake", "readiness"] }),
    ]);
  };

  const copyConfigurationPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      notify(`Copied configuration path: ${path}`, "success");
    } catch {
      notify(`Copy this path manually: ${path}`, "info");
    }
  };

  const newConnectionProvider = (type: ModelProvider["type"]) => {
    const existingOllama = type === "ollama"
      ? providerData.data?.providers.find((provider) => provider.type === "ollama")
      : undefined;
    const provider = blankProvider(type);
    if (existingOllama) provider.base_url = existingOllama.base_url;
    const existingIds = new Set(providerData.data?.providers.map((item) => item.id) ?? []);
    if (existingIds.has(provider.id)) {
      let suffix = 2;
      while (existingIds.has(`${provider.id}-${suffix}`)) suffix += 1;
      provider.id = `${provider.id}-${suffix}`;
    }
    return provider;
  };
  const openNewConnection = () => {
    setEditingProviderId(null);
    setProviderForm(newConnectionProvider("openai"));
    setApiKey("");
    setConnectionOpen(true);
  };
  const openExistingConnection = (provider: ModelProvider) => {
    setEditingProviderId(provider.id);
    setProviderForm(provider);
    setApiKey("");
    setConnectionOpen(true);
  };

  const followWorkflowStep = (step: WorkflowStepId) => {
    if (step === "embedding" || step === "language") {
      const provider = (providerData.data?.providers ?? []).find((item) => item.enabled && (step === "embedding" ? item.default_embedding : item.default_chat));
      if (provider) openExistingConnection(provider);
      else document.getElementById("setup-model-connections")?.scrollIntoView({ behavior: "smooth", block: "center" });
    } else if (step === "extractor") {
      setExpandedCapability("extractor");
      document.getElementById("setup-extractor-heading")?.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      navigate(`/intake?step=${step}`);
    }
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

  const removeConnection = async (provider: ModelProvider) => {
    if (!window.confirm(`Remove model connection “${provider.id}”? Existing semantic indexes remain on disk but cannot be extended with this connection.`)) return;
    try {
      await deleteModelProvider(provider.id);
      notify(`${provider.id} was removed.`);
      await refreshSetup();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not remove the model connection.", "error");
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
      const health = await checkModelProvider(provider.id);
      const installedName = health.models.find((model) => modelNameMatches(model, recommendation.model))
        ?? recommendation.model;
      const updatedProvider = recommendation.capability === "embedding"
        ? { ...provider, implicit: false, embedding_model: installedName }
        : { ...provider, implicit: false, chat_model: installedName, synthesis_model: installedName };
      await createModelProvider(updatedProvider);
      setProviderForm((current) => current.id === provider.id ? { ...current, ...updatedProvider } : current);
      const validatedHealth = await checkModelProvider(provider.id);
      setProviderHealth((current) => ({ ...current, [provider.id]: validatedHealth }));
      const embeddingTest = validatedHealth.capabilities?.embedding;
      notify(recommendation.capability === "embedding"
        ? embeddingTest?.ok
          ? `${recommendation.display_name} is installed, selected, and ready. Build semantic embeddings in Intake for documents already in OSII.`
          : `${recommendation.display_name} is installed and selected, but its embedding test failed: ${embeddingTest?.detail ?? "unknown error"}`
        : `${recommendation.display_name} is installed and selected for chat, synthesis, and wikis.`,
      recommendation.capability === "embedding" && !embeddingTest?.ok ? "error" : "success");
      await refreshSetup();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Model download failed.", "error");
    }
  };

  const selectInstalledModel = async (
    provider: ModelProvider,
    recommendation: OllamaRecommendation,
    installedName: string,
  ) => {
    const updatedProvider = recommendation.capability === "embedding"
      ? { ...provider, implicit: false, embedding_model: installedName }
      : { ...provider, implicit: false, chat_model: installedName, synthesis_model: installedName };
    try {
      await createModelProvider(updatedProvider);
      setProviderForm((current) => current.id === provider.id ? { ...current, ...updatedProvider } : current);
      const health = await checkModelProvider(provider.id);
      setProviderHealth((current) => ({ ...current, [provider.id]: health }));
      notify(recommendation.capability === "embedding"
        ? `${recommendation.display_name} is selected. Build semantic embeddings in Intake for documents already in OSII.`
        : `${recommendation.display_name} is selected for chat, synthesis, and wikis.`);
      await refreshSetup();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not select the installed model.", "error");
    }
  };

  const addProcessor = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createProcessorEndpoint(processorForm);
      setProcessorForm({ base_url: "http://", model_connection: "" });
      notify("Running processor discovered and registered.");
      await queryClient.invalidateQueries({ queryKey: ["admin", "processors"] });
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not add the service.", "error");
    }
  };

  const removeProcessor = async (processor: ProcessorEndpoint) => {
    try {
      await deleteProcessorEndpoint(processor.id);
      notify(`${processor.display_name}: registration removed.`);
      await queryClient.invalidateQueries({ queryKey: ["admin", "processors"] });
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not remove the service.", "error");
    }
  };

  const changeProcessorBinding = async (processor: ProcessorEndpoint, modelConnection: string) => {
    try {
      await updateProcessorEndpoint(processor.id, { model_connection: modelConnection });
      notify(`${processor.display_name}: model connection changed to ${modelConnection || "the library default"}.`);
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not change the model connection.", "error");
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
      await saveProcessorSettings(item.id, {...settings.data?.settings[item.id], ...capabilityDraft});
      setEditingCapability(null);
      notify(`${item.display_name}: settings saved.`);
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
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
  useEffect(() => {
    if (!providerData.data || !data || !requestedStep || focusedWorkflowStep.current === requestedStep) return;
    if (!["embedding", "language", "extractor"].includes(requestedStep)) return;
    focusedWorkflowStep.current = requestedStep;
    followWorkflowStep(requestedStep as WorkflowStepId);
  }, [requestedStep, providerData.data, data]);
  const configurationErrors = Object.entries(data?.configuration?.errors ?? {});
  const savedEndpointMatches = providerData.data?.providers.some(provider => provider.id === editingProviderId && provider.base_url === providerForm.base_url.replace(/\/$/, ""));
  const discoveredModels = catalogQueried ? catalogModels : (savedEndpointMatches ? providerHealth[providerForm.id]?.models ?? [] : []).map(id => ({ id, name: id, capabilities: [] }));

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

  const routeChoiceSupported = (id: string, route: ExtractorRoute) => {
    const item = capabilityMethods("extractor").find(item => item.id === id || item.aliases?.includes(id));
    const extensions = item?.descriptor?.capabilities?.file_extensions;
    return !extensions?.length || extensions.includes("*") || route.extensions.every(ext => extensions.includes(ext));
  };
  const routeChoiceStyle = (id: string) => ({ color: capabilityMethods("extractor").find(item => item.id === id || item.aliases?.includes(id))?.available ? "text.primary" : "text.disabled" });
  const renderExtractionRouting = () => (
    <Paper variant="outlined" sx={{ p: 2, mt: 3, borderTop: "4px solid", borderTopColor: "secondary.main", bgcolor: "action.hover" }}><Stack spacing={1.5}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1} alignItems={{ md: "center" }}>
        <Stack spacing={0.5}><Stack direction="row" alignItems="center"><Typography variant="h6" fontWeight={700}>Extraction routing defaults</Typography><IconButton aria-label="About extraction routing defaults" onClick={() => setRoutingHelp(true)}><HelpOutlineIcon /></IconButton></Stack><Typography variant="body2" color="text.secondary">Choose a reader and fallback order for each file type.</Typography><Typography variant="caption" sx={{ overflowWrap: "anywhere" }}>Saved to: <code>{extractorRoutes.data?.path ?? "Loading configuration path…"}</code></Typography></Stack>
        <Stack direction="row" spacing={1}><Button component="label" variant="outlined">Load TOML<input hidden type="file" accept=".toml" onChange={async (event) => {
          const file = event.target.files?.[0]; event.target.value = "";
          if (!file) return;
          try {
            if (file.size > 1024 * 1024) throw new Error("Choose a TOML file no larger than 1 MiB.");
            const result = await apiJson<{ok: boolean; routes: ExtractorRoute[]; errors?: string[]; warnings?: string[]}>("/api/extractor-routes/import", {method: "POST", json: {toml: await file.text()}});
            if (!result.ok) throw new Error(result.errors?.join(" ") || "Invalid routing TOML.");
            setRouteDraft(result.routes); notify("TOML loaded. Review the rules, then Save routes.");
          } catch (error) { notify(error instanceof Error ? error.message : "Could not load TOML.", "error"); }
        }} /></Button><Button variant="outlined" onClick={addRoute}>Add file-type rule</Button><Button variant="contained" disabled={!routeDraft || savingRoutes} onClick={() => void persistRoutes()}>{savingRoutes ? "Saving…" : "Save routes"}</Button></Stack>
      </Stack>
      {extractorRoutes.isLoading ? <LinearProgress /> : null}
      {currentRoutes.map((route, index) => {
        const availableIds = capabilityMethods("extractor").map((item) => item.id);
        const choices = Array.from(new Set([route.extractor, ...route.fallbacks, ...availableIds]));
        return <Paper key={`${route.name}-${index}`} variant="outlined" sx={{ p: 1.5 }}><Stack spacing={1}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }} flexWrap="wrap" useFlexGap>
            <TextField size="small" label="File extensions" value={route.extensions.join(", ")} onChange={(event) => updateRoute(index, { extensions: event.target.value.split(",").map((value) => value.trim().toLowerCase()).filter(Boolean) })} helperText="Comma-separated, or * for everything else" sx={{ minWidth: 250 }} />
            <TextField select size="small" label="Primary extractor" value={route.extractor} onChange={(event) => updateRoute(index, { extractor: event.target.value, fallbacks: route.fallbacks.filter((item) => item !== event.target.value) })} sx={{ minWidth: 230 }}>{choices.map((id) => <MenuItem key={id} value={id} disabled={!routeChoiceSupported(id, route)} sx={routeChoiceStyle(id)}>{capabilityMethods("extractor").find((item) => item.id === id || item.aliases?.includes(id))?.display_name ?? id}</MenuItem>)}</TextField>
            <Typography aria-hidden color="text.secondary" fontSize="1.4rem">→</Typography>
            <TextField select size="small" label="First fallback" value={route.fallbacks[0] ?? ""} onChange={(event) => updateRoute(index, { fallbacks: event.target.value ? [event.target.value, ...route.fallbacks.slice(1).filter((id) => id !== event.target.value)] : [] })} sx={{ minWidth: 220 }}><MenuItem value="">No fallback</MenuItem>{choices.filter((id) => id !== route.extractor).map((id) => <MenuItem key={id} value={id} disabled={!routeChoiceSupported(id, route)} sx={routeChoiceStyle(id)}>{capabilityMethods("extractor").find((item) => item.id === id || item.aliases?.includes(id))?.display_name ?? id}</MenuItem>)}</TextField>
            <Typography aria-hidden color="text.secondary" fontSize="1.4rem">→</Typography>
            <TextField select size="small" label="Second fallback" disabled={!route.fallbacks[0]} value={route.fallbacks[1] ?? ""} onChange={(event) => updateRoute(index, { fallbacks: event.target.value ? [route.fallbacks[0], event.target.value, ...route.fallbacks.slice(2).filter((id) => id !== event.target.value)] : route.fallbacks.slice(0, 1) })} sx={{ minWidth: 220 }}><MenuItem value="">No second fallback</MenuItem>{choices.filter((id) => id !== route.extractor && id !== route.fallbacks[0]).map((id) => <MenuItem key={id} value={id} disabled={!routeChoiceSupported(id, route)} sx={routeChoiceStyle(id)}>{capabilityMethods("extractor").find((item) => item.id === id || item.aliases?.includes(id))?.display_name ?? id}</MenuItem>)}</TextField>
          </Stack>
          <Button size="small" color="error" sx={{ alignSelf: "flex-end" }} onClick={() => setRouteDraft(currentRoutes.filter((_, routeIndex) => routeIndex !== index))}>Remove rule</Button>
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
        const processor = processors.data?.processors.find(p => p.processor_id === item.id || p.id === item.id);
        const binding = processor?.model_access?.bindings?.chat ?? "";
        const languageConnections = (providerData.data?.providers ?? []).filter(provider => provider.enabled && provider.chat_model);
        const isSelected = kind === "extractor"
          ? currentRoutes.some((route) => [route.extractor, ...route.fallbacks].some(
            (id) => id === item.id || item.aliases?.includes(id),
          ))
          : selected?.id === item.id || item.aliases?.includes(selected?.id ?? "");
        return <Box key={item.id} sx={{ color: item.available ? "text.primary" : "text.disabled", bgcolor: item.available ? "transparent" : "action.hover", px: 1, py: 1, borderBottom: "1px solid", borderColor: "divider", "&:last-child": { borderBottom: 0 } }}><Stack spacing={0.6}>
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2" fontWeight={700}>{item.display_name}</Typography>
            {isSelected ? <Chip size="small" color="primary" label={kind === "extractor" ? "In routing" : "Default"} /> : null}
            {item.origin ? <Chip size="small" variant="outlined" label={item.origin.label} /> : null}
            <Chip size="small" color={item.available ? "success" : "default"} label={item.available ? "Available" : "Unavailable"} />
          </Stack>
          <Typography variant="caption" color="text.secondary">{item.description}</Typography>

          {!item.available ? <Typography variant="caption" color="text.secondary">{item.detail}</Typography> : null}
          {processor?.model_requirements?.chat ? <Stack direction={{xs: "column", sm: "row"}} spacing={1} alignItems={{sm: "center"}}>
            <TextField select size="small" label="Writing model endpoint" value={binding} onChange={event => void changeProcessorBinding(processor, event.target.value)} sx={{minWidth: 280}}>
              <MenuItem value="">Automatic · {processor.resolved_models?.chat ?? "connect a language model"}</MenuItem>
              {binding && !languageConnections.some(provider => provider.id === binding) ? <MenuItem value={binding}>{binding} · unavailable</MenuItem> : null}
              {languageConnections.map(provider => <MenuItem key={provider.id} value={provider.id}>{provider.id} · {provider.chat_model} · {provider.base_url}</MenuItem>)}
            </TextField>
            {processor.model_error ? <Typography variant="caption" color="error">{processor.model_error}</Typography> : null}
            <Button size="small" onClick={() => openNewConnection()}>Connect model</Button>
          </Stack> : null}
          {item.id === "tika" ? <Stack direction={{xs: "column", sm: "row"}} spacing={1}><TextField size="small" label="Apache Tika endpoint" value={tikaEndpoint ?? String(settings.data?.settings.tika?.tika_endpoint ?? "http://127.0.0.1:9998")} onChange={event => setTikaEndpoint(event.target.value)} sx={{minWidth: 300}} /><Button size="small" onClick={async () => {
            const endpoint = String(tikaEndpoint ?? settings.data?.settings.tika?.tika_endpoint ?? "http://127.0.0.1:9998");
            try { const url = new URL(endpoint); if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error("invalid"); }
            catch { notify("Enter an HTTP(S) base URL without credentials, query, or fragment.", "error"); return; }
            try { await saveProcessorSettings("tika", {...settings.data?.settings.tika, tika_endpoint: endpoint}); notify("Apache Tika endpoint saved."); await queryClient.invalidateQueries({queryKey: ["admin"]}); }
            catch (error) { notify(error instanceof Error ? error.message : "Could not save endpoint.", "error"); }
          }}>Save endpoint</Button></Stack> : null}
          {Object.keys(schema?.properties ?? {}).length ? <Button size="small" sx={{ alignSelf: "flex-start", px: 0 }} onClick={() => editingCapability === item.id ? setEditingCapability(null) : editCapability(item)}>{editingCapability === item.id ? "Hide settings" : "Settings"}</Button> : null}
          {editingCapability === item.id ? <Stack spacing={1}>{Object.entries(schema?.properties ?? {}).map(([name, property]) => <ConfigInput key={name} name={name} property={property} value={capabilityDraft[name]} onChange={(value) => setCapabilityDraft((current) => ({ ...current, [name]: value }))} />)}<Button variant="contained" size="small" onClick={() => void saveCapability(item)} sx={{ alignSelf: "flex-start" }}>Save settings</Button></Stack> : null}
          <IconButton size="small" aria-label={`About ${item.display_name} implementation and configuration`} onClick={() => setSourceHelp(item)} sx={{alignSelf: "flex-start"}}><HelpOutlineIcon fontSize="small" /></IconButton>
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

  return <Stack spacing={3} sx={{ maxWidth: 1100, mx: "auto" }}>
    <Typography variant="h5" fontWeight={750}>Setup</Typography>
    <Dialog open={Boolean(sourceHelp)} onClose={() => setSourceHelp(null)} fullWidth maxWidth="sm"><DialogTitle>{sourceHelp?.display_name}</DialogTitle><DialogContent><Stack spacing={1} sx={{overflowWrap: "anywhere"}}><Typography>{sourceHelp?.description}</Typography><Typography variant="body2">Processor: <code>{sourceHelp?.id}</code></Typography>{sourceHelp?.base_url ? <Typography variant="body2">Service address: <code>{sourceHelp.base_url}</code></Typography> : null}<Typography variant="body2">Registration source: <code>{sourceHelp?.origin?.implementation}</code></Typography><Typography variant="body2">Configuration overrides: <code>{sourceHelp?.origin?.configuration_file}</code></Typography>{sourceHelp?.origin?.endpoint_source ? <Typography variant="body2">Endpoint configuration: {sourceHelp.origin.endpoint_source}</Typography> : null}<Typography variant="body2">Built-in registrations provide defaults. The configuration file stores your overrides, so it can be nearly empty. Independently deployed tool code lives in osii-toolbox/; Core adapters live in osii-core/osii/extraction/. Model-backed tools use the Writing model endpoint selector in their service row.</Typography></Stack></DialogContent><DialogActions><Button onClick={() => setSourceHelp(null)}>Close</Button></DialogActions></Dialog>
    <Dialog open={routingHelp} onClose={() => setRoutingHelp(false)} maxWidth="sm" fullWidth><DialogTitle>Extraction routing defaults</DialogTitle><DialogContent><Stack spacing={2}>
      <Typography>Rules are checked from top to bottom. The first matching file extension chooses the primary extractor. If it fails, OSII tries the fallbacks from left to right. Put the * catch-all last.</Typography>
      <Typography>These are Intake defaults; an explicit reader choice for a batch overrides them. Each reader must support all file types in its rule, including fallbacks. Unavailable services are gray; their saved rules remain so a temporary outage does not change your configuration.</Typography>
      <Typography>Save routes writes the active tools.toml shown in this section. Load TOML reads [[routes.extractor]] rules for review; it does not save or replace other tool settings until you click Save routes.</Typography>
      <Typography>To add your own extractor, start with the code in <code>osii-core/osii/extraction/</code> and the independent tools in <code>osii-toolbox/</code>. Read <code>docs/reference/extractor-routing.md</code> and <code>docs/reference/processor-api/extraction.md</code>. Build a tool that follows OSII’s Processor API: it receives selected files, declares the file types it accepts, and returns text and source locations. Register its service address in Setup.</Typography>
    </Stack></DialogContent><DialogActions><Button onClick={() => setRoutingHelp(false)}>Close</Button></DialogActions></Dialog>
    <WorkflowProgress readiness={data?.readiness} checking={setup.isLoading} failed={setup.isError} onStep={followWorkflowStep} />

    {!connectionOpen && !serviceLogs ? renderNotice() : null}
    {setup.isError ? <Alert severity="error"><strong>OSII&apos;s backend is not responding.</strong> Check that the library is running, then refresh this page.</Alert> : null}
    {configurationErrors.map(([file, detail]) => <Alert key={file} severity="error"><strong>{file}.toml was not loaded.</strong> {detail} OSII is continuing with the last valid configuration.</Alert>)}

    <Stack spacing={1.25}>
      <Stack id="setup-model-connections" direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <Typography variant="h6" fontWeight={700}>Model connections</Typography>
        <Button variant="contained" color="secondary" disabled={!providerData.data} onClick={openNewConnection}>Add connection</Button>
      </Stack>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}><Stack spacing={2} divider={<Divider flexItem />}>
        {(data?.providers ?? []).filter((provider) => provider.enabled && !(provider.type === "ollama" && provider.implicit)).map((provider) => <Stack key={provider.id} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1} alignItems={{ sm: "center" }}>
          <Stack spacing={0.75} minWidth={0}>
            <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="body2" fontWeight={700}>{provider.id}</Typography>
              <ConnectionEndpointStatus provider={provider} generation={data?.configuration.generation} />
              {provider.default_chat ? <Chip size="small" label="Default language" /> : null}
              {provider.default_embedding ? <Chip size="small" label="Default embedding" /> : null}
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{provider.base_url}</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {provider.chat_model || provider.synthesis_model ? <Typography variant="caption">Language · {provider.chat_model || provider.synthesis_model}</Typography> : null}
              {provider.embedding_model ? <Typography variant="caption">Embedding · {provider.embedding_model}</Typography> : null}
            </Stack>
          </Stack>
          <Stack direction="row" spacing={1} flexShrink={0}><Button size="small" onClick={() => openExistingConnection(provider)}>Configure</Button><Button size="small" onClick={() => void checkConnection(provider)}>Test models</Button></Stack>
        </Stack>)}
        {!data?.providers?.some((provider) => provider.enabled && !(provider.type === "ollama" && provider.implicit)) ? <Typography variant="body2" color="text.secondary">{setup.isError ? "Connections unavailable" : !data ? "Loading connections…" : "No enabled connections"}</Typography> : null}
      </Stack></Paper>
    </Stack>

    <Stack spacing={1.25}>
      <Typography variant="h6" fontWeight={700}>Processing defaults</Typography>
      {renderCapabilityDrawer("extractor")}
      {renderCapabilityDrawer("synthesizer")}
      {renderCapabilityDrawer("embedder")}
      {renderCapabilityDrawer("enricher")}
    </Stack>


    <Accordion variant="outlined" disableGutters elevation={0} sx={{ borderRadius: "12px !important", overflow: "hidden" }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography fontWeight={700}>Advanced &amp; diagnostics</Typography></AccordionSummary>
      <AccordionDetails><Stack spacing={2}>
        {data?.configuration ? <Stack spacing={0.75}><Typography variant="body2" fontWeight={700}>Active configuration · {data.configuration.active_profile}</Typography><Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}><code>{data.configuration.directory}</code></Typography><Typography variant="body2" color="text.secondary">Development defaults to the checkout&apos;s ignored osii-data/config/ directory. Installed launchers use a writable profile workspace. OSII_CONFIG_DIR overrides either location. Originals and portable .osii artifacts are separate.</Typography>{Object.entries(data.configuration.files).map(([name, path]) => <Stack key={name} direction="row" spacing={1} alignItems="center"><Typography variant="caption" sx={{ overflowWrap: "anywhere", flex: 1 }}><code>{path}</code></Typography><Button size="small" sx={{ flexShrink: 0 }} onClick={() => void copyConfigurationPath(path)}>Copy path</Button></Stack>)}</Stack> : null}
        <Accordion variant="outlined" disableGutters><AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography fontWeight={700}>Service status</Typography></AccordionSummary><AccordionDetails><Stack divider={<Divider flexItem />}>
          <Typography variant="body2" color="text.secondary">The launcher normally starts and stops container services. The controls below apply only to a local development session.</Typography>
          {(data?.services ?? []).map((service) => <ServiceRow key={service.id} service={service} busy={serviceBusy === service.id} onAction={(action) => void runServiceAction(service, action)} onLogs={() => void showLogs(service)} />)}
          {!data?.service_control_available ? <Alert severity="info">Lifecycle controls are available with <code>make dev</code> or <code>.\scripts\osii.ps1 dev</code>. This deployment reports health only.</Alert> : null}
        </Stack></AccordionDetails></Accordion>

        <Accordion variant="outlined" disableGutters><AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography fontWeight={700}>Connection maintenance</Typography></AccordionSummary><AccordionDetails><Stack spacing={1.25}>
          {(data?.providers ?? []).map((provider) => <Paper key={provider.id} variant="outlined" sx={{ p: 1.5 }}><Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}><Stack><Typography variant="body2" fontWeight={700}>{provider.id}</Typography><Typography variant="caption" color="text.secondary">{provider.base_url} · priority {provider.priority} · {provider.enabled ? "enabled" : "disabled"}</Typography></Stack><Stack direction="row" spacing={1}><Button size="small" onClick={() => openExistingConnection(provider)}>Edit</Button><Button size="small" onClick={() => void checkConnection(provider)}>Test</Button>{provider.credential_present && provider.credential_source === "repo_env" ? <Button size="small" color="error" onClick={() => void forgetCredential(provider)}>Forget key</Button> : null}<Button size="small" color="error" onClick={() => void removeConnection(provider)}>Remove</Button></Stack></Stack></Paper>)}
        </Stack></AccordionDetails></Accordion>

        <Accordion variant="outlined" disableGutters><AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography fontWeight={700}>Custom Processor API services</Typography></AccordionSummary><AccordionDetails><Stack spacing={1.5}>
          <Typography variant="body2" color="text.secondary">Paste a running service&apos;s base address. OSII reads its descriptor and learns its name, capability, scopes, outputs, and model needs automatically.</Typography>
          <Box component="form" onSubmit={(event) => void addProcessor(event)}><Stack spacing={1}><TextField size="small" label="Running processor URL" required value={processorForm.base_url} onChange={(event) => setProcessorForm({ ...processorForm, base_url: event.target.value })} helperText="For example, http://127.0.0.1:8099" /><TextField size="small" select label="Writing model" value={processorForm.model_connection} onChange={(event) => setProcessorForm({ ...processorForm, model_connection: event.target.value })}><MenuItem value="">Library default</MenuItem>{(providerData.data?.providers ?? []).filter((provider) => provider.chat_model).map((provider) => <MenuItem key={provider.id} value={provider.id}>{provider.id} · {provider.chat_model}</MenuItem>)}</TextField><Button type="submit" variant="contained" sx={{ alignSelf: "flex-start" }}>Discover and register</Button></Stack></Box>
          {(processors.data?.processors ?? []).map((processor) => {
            const binding = processor.model_access?.mode === "gateway" ? Object.values(processor.model_access.bindings ?? {})[0] : null;
            return <Stack key={processor.id} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}><Stack><Typography variant="body2" fontWeight={700}>{processor.display_name}</Typography><Typography variant="caption" color="text.secondary">{processor.kind} · {processor.base_url} · {binding ? `Language model: ${binding}` : processor.model_requirements?.chat ? "Library default" : "No model required"}</Typography></Stack><Stack direction="row" spacing={1}><Button size="small" onClick={() => void testProcessor(processor, false)}>Health</Button><Button size="small" variant="outlined" onClick={() => void testProcessor(processor, true)}>Descriptor</Button><Button size="small" color="error" onClick={() => void removeProcessor(processor)}>Remove</Button></Stack></Stack>;
          })}
        </Stack></AccordionDetails></Accordion>
      </Stack></AccordionDetails>
    </Accordion>

    <Stack direction="row" justifyContent="flex-end" sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2 }}>
      <Button variant="contained" color="secondary" onClick={() => navigate("/intake")} disabled={!data?.extraction_ready}>Continue to Intake →</Button>
    </Stack>

    <Dialog open={connectionOpen} onClose={() => setConnectionOpen(false)} fullWidth maxWidth="sm"><Box component="form" onSubmit={(event) => void saveConnection(event)}>
      <DialogTitle>{editingProviderId ? "Configure connection" : "Add connection"}</DialogTitle><DialogContent>
      {connectionOpen && !serviceLogs ? renderNotice() : null}
      <Stack spacing={1.5} sx={{ pt: 0.5 }}>
        <TextField select label="Connection" value={providerForm.type} disabled={Boolean(editingProviderId)} onChange={(event) => { setProviderForm(newConnectionProvider(event.target.value as ModelProvider["type"])); setApiKey(""); }} helperText="Use your endpoint's URL, model names, and API key. For a local model server, choose Ollama."><MenuItem value="openai">OpenAI-compatible endpoint</MenuItem><MenuItem value="ollama">Ollama (local model server)</MenuItem></TextField>
        <TextField label="Connection name" required disabled={Boolean(editingProviderId)} value={providerForm.id} onChange={(event) => setProviderForm({ ...providerForm, id: event.target.value.trim().toLowerCase() })} helperText="A stable name such as OpenRouter or Corporate." />
        <EndpointFields required onDiscover={() => void findModels()} discovering={discoveringModels} baseUrl={providerForm.base_url} onBaseUrl={base_url => setProviderForm({ ...providerForm, base_url })}
          apiKey={apiKey} onApiKey={setApiKey} credentialPresent={providerForm.credential_present}
          credentialWritable={providerForm.credential_writable !== false} showCredential={providerForm.type !== "ollama"}
          urlHelp={providerForm.type === "ollama" ? "Ollama server address, such as http://localhost:11434." : "Use the OpenAI-compatible API base address."}
          credentialHelp={providerForm.credential_help ?? `Saved locally in ${data?.configuration.files.secrets ?? "secrets.env"}. Never sent to Toolbox processors.`} />
        {providerForm.type === "ollama" && <Alert severity="info" icon={false}>Install and start Ollama yourself. OSII can inspect installed models and download the approved starters.</Alert>}
        <ModelPicker label="Language model" value={providerForm.chat_model} options={discoveredModels.filter(model => !model.capabilities.length || model.capabilities.includes("chat"))}
          onChange={model => setProviderForm(current => ({ ...current, chat_model: model, synthesis_model: model }))} helperText="Choose an available model for chat, summaries, and wiki generation." />
        <FormControlLabel control={<Switch checked={Boolean(providerForm.default_chat)} disabled={!providerForm.chat_model} onChange={(event) => setProviderForm({ ...providerForm, default_chat: event.target.checked })} />} label="Use this connection by default for chat and synthesis" />
        <ModelPicker label="Embedding model (optional)" value={providerForm.embedding_model} options={discoveredModels.filter(model => !model.capabilities.length || model.capabilities.includes("embedding"))}
          onChange={model => setProviderForm(current => ({ ...current, embedding_model: model }))} helperText="Choose a model for semantic search. Keyword search remains available without it." />
        <FormControlLabel control={<Switch checked={Boolean(providerForm.default_embedding)} disabled={!providerForm.embedding_model} onChange={(event) => setProviderForm({ ...providerForm, default_embedding: event.target.checked })} />} label="Use this connection by default for semantic embeddings" />
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
          const health = providerHealth[providerForm.id];
          const installedName = health?.models.find((model) => modelNameMatches(model, recommendation.model));
          const selectedName = recommendation.capability === "embedding"
            ? providerForm.embedding_model
            : providerForm.chat_model;
          const selected = Boolean(
            installedName
            && !providerForm.implicit
            && modelNameMatches(installedName, selectedName),
          );
          return <Paper key={recommendation.model} variant="outlined" sx={{ p: 1.25 }}><Stack spacing={0.5}><Stack direction="row" justifyContent="space-between" spacing={1}><Stack><Typography variant="body2" fontWeight={700}>{recommendation.display_name}</Typography><Typography variant="caption" color="text.secondary">{recommendation.model} · {recommendation.size_label} · {recommendation.publisher}</Typography></Stack>{installedName ? <Stack direction="row" spacing={0.75} alignItems="center"><Chip size="small" color="success" label={selected ? "Installed · selected" : "Installed"} />{!selected ? <Button size="small" variant="outlined" onClick={() => void selectInstalledModel(providerForm, recommendation, installedName)}>Use this model</Button> : null}</Stack> : <Button size="small" variant="outlined" disabled={active || !health} onClick={() => void installModel(providerForm, recommendation)}>{active ? "Downloading…" : health ? "Download" : "Checking…"}</Button>}</Stack>{active ? <LinearProgress variant={progress === undefined ? "indeterminate" : "determinate"} value={progress} /> : null}{job?.status === "error" ? <Typography variant="caption" color="error">{job.detail}</Typography> : null}{installedName && recommendation.capability === "embedding" ? <Typography variant="caption" color="text.secondary">The model enables semantic processing. Existing documents still need a semantic-embedding run from Intake.</Typography> : null}</Stack></Paper>;
        })}</Stack> : null}
      </Stack></DialogContent><DialogActions><Button onClick={() => setConnectionOpen(false)}>Close</Button><Button type="submit" variant="contained" disabled={savingConnection}>{savingConnection ? "Saving and checking…" : "Save and check connection"}</Button></DialogActions>
    </Box></Dialog>

    <Dialog open={Boolean(serviceLogs)} onClose={() => setServiceLogs(null)} fullWidth maxWidth="md"><DialogTitle>{serviceLogs?.title} logs</DialogTitle><DialogContent>{serviceLogs ? renderNotice() : null}<Box component="pre" sx={{ bgcolor: "grey.950", color: "grey.100", p: 1.5, borderRadius: 1, maxHeight: 420, overflow: "auto", whiteSpace: "pre-wrap", fontSize: "0.75rem" }}>{serviceLogs?.lines.join("\n") || "No recent output."}</Box></DialogContent><DialogActions><Button onClick={() => setServiceLogs(null)}>Close</Button></DialogActions></Dialog>
  </Stack>;
}
