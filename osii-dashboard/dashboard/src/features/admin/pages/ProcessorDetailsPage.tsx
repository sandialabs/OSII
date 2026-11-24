import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  Divider, IconButton, LinearProgress, MenuItem, Paper, Stack, TextField, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import {
  checkProcessorEndpoint, controlCapabilityService, deleteProcessorEndpoint,
  getCapabilityServiceLogs, getProcessorSettings, getSetupSummary, listModelProviders,
  listProcessorEndpoints, saveProcessorSettings, updateProcessorEndpoint,
} from "../../../api/queue";
import type { ModelProvider, ProcessorConfigProperty, ProcessorEndpoint } from "../../../api/types";
import { ProcessorConfigInput } from "../../queue/components/ProcessorConfigInput";
import { ProcessorStartupSettings } from "../components/ProcessorStartupSettings";
import { ServiceRow } from "../components/ServiceRow";
import { matchingEndpoint } from "../processorDetails";

const SETUP_PATH = "/admin/processors";
const emptySettings: Record<string, unknown> = {};
const modelFields = [
  { capability: "chat", field: "chat_model", label: "Writing model" },
  { capability: "embedding", field: "embedding_model", label: "Embedding model" },
] as const;
type RunAction = (action: () => Promise<string | void>) => Promise<void>;

function RuntimeSettings({ id, saved, properties, busy, run }: {
  id: string;
  saved: Record<string, unknown>;
  properties: Record<string, ProcessorConfigProperty>;
  busy: boolean;
  run: RunAction;
}) {
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  return <Paper variant="outlined" component="form" sx={{ p: 2 }} onSubmit={event => {
    event.preventDefault();
    void run(async () => {
      await saveProcessorSettings(id, { ...saved, ...draft });
      setDraft({});
      return "Processor settings saved.";
    });
  }}>
    <Stack spacing={1.5}>
      <Typography variant="h6" component="h2">Processing settings</Typography>
      {Object.entries(properties).map(([name, property]) => <ProcessorConfigInput key={name} name={name} property={property}
        value={draft[name] ?? saved[name] ?? property.default} onChange={value => setDraft(current => ({ ...current, [name]: value }))} />)}
      <Button type="submit" variant="contained" disabled={busy || !Object.keys(draft).length} sx={{ alignSelf: "start" }}>Save settings</Button>
    </Stack>
  </Paper>;
}

function EndpointSettings({ endpoint, providers, busy, run }: {
  endpoint: ProcessorEndpoint;
  providers: ModelProvider[];
  busy: boolean;
  run: RunAction;
}) {
  const [address, setAddress] = useState(endpoint.base_url);
  const savedBindings = endpoint.model_access?.bindings ?? {};
  const [bindings, setBindings] = useState(savedBindings);
  const supportedModels = modelFields.filter(({capability}) => endpoint.model_requirements?.[capability]);
  const editable = !endpoint.built_in;
  const changed = address.trim() !== endpoint.base_url
    || supportedModels.some(({capability}) => (bindings[capability] ?? "") !== (savedBindings[capability] ?? ""));

  return <Paper variant="outlined" component="form" sx={{ p: 2 }} onSubmit={event => {
    event.preventDefault();
    void run(async () => {
      await updateProcessorEndpoint(endpoint.id, {
        model_access: { mode: "gateway", bindings }, base_url: editable ? address.trim() : undefined, preserve_processor: true,
      });
      return "Connection settings saved.";
    });
  }}>
    <Stack spacing={1.5}>
      <Typography variant="h6" component="h2">Service connection</Typography>
      {editable
        ? <TextField size="small" label="Processor address" type="url" required value={address} onChange={event => setAddress(event.target.value)} />
        : <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{endpoint.base_url}</Typography>}
      {supportedModels.map(({capability, field, label}) => {
        const options = providers.filter(provider => provider.enabled && provider[field]);
        const selected = bindings[capability] ?? "";
        const resolved = options.find(provider => provider.id === endpoint.resolved_models?.[capability]);
        return <TextField key={capability} select size="small" label={label} value={selected}
          onChange={event => setBindings(values => ({ ...values, [capability]: event.target.value }))}>
          <MenuItem value="">Library default{resolved && !savedBindings[capability] ? " · " + resolved[field] : ""}</MenuItem>
          {selected && !options.some(provider => provider.id === selected) && <MenuItem value={selected}>{selected} · Unavailable</MenuItem>}
          {options.map(provider => <MenuItem key={provider.id} value={provider.id}>{provider.display_name || provider.id} · {provider[field]}</MenuItem>)}
        </TextField>;
      })}
      {endpoint.model_error && <Alert severity="warning">{endpoint.model_error}</Alert>}
      {(supportedModels.length > 0 || editable) && <Button type="submit" variant="contained" disabled={busy || !changed} sx={{ alignSelf: "start" }}>Save connection</Button>}
    </Stack>
  </Paper>;
}

export function ProcessorDetailsPage() {
  const { processorId, registrationId } = useParams();
  const client = useQueryClient();
  const navigate = useNavigate();
  const setup = useQuery({ queryKey: ["admin", "setup"], queryFn: getSetupSummary });
  const endpoints = useQuery({ queryKey: ["admin", "processors"], queryFn: listProcessorEndpoints });
  const settings = useQuery({ queryKey: ["admin", "processor-settings"], queryFn: getProcessorSettings });
  const providers = useQuery({ queryKey: ["admin", "model-providers"], queryFn: listModelProviders });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ severity: "error" | "success"; text: string } | null>(null);
  const [help, setHelp] = useState(false);
  const [logs, setLogs] = useState<string[] | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const readiness = setup.data?.readiness;
  const entries = readiness ? [...readiness.extractors, ...readiness.synthesizers, ...readiness.embedders, ...readiness.enrichers] : [];
  const registration = endpoints.data?.processors.find(endpoint => endpoint.id === registrationId);
  const item = registration
    ? entries.find(candidate => candidate.id === registration.processor_id && candidate.base_url === registration.base_url)
    : entries.find(candidate => candidate.id === processorId);
  const endpoint = registration ?? (item && matchingEndpoint(item, endpoints.data?.processors ?? []));
  const id = endpoint?.processor_id ?? item?.id ?? endpoint?.id ?? "";
  const name = item?.display_name ?? endpoint?.display_name;
  const removalAction = endpoint?.built_in ? "Disable" : "Remove";
  const address = endpoint?.base_url ?? item?.base_url;
  const properties = item?.config_schema?.properties ?? item?.descriptor?.config_schema?.properties ?? endpoint?.config_schema?.properties ?? {};
  const service = address ? setup.data?.services.reduce<typeof setup.data.services[number] | undefined>((match, candidate) => {
    const url = candidate.url.replace(/\/$/, "");
    return url && (address === url || address.startsWith(url + "/")) && url.length > (match?.url.length ?? 0) ? candidate : match;
  }, undefined) : undefined;
  const origin = item?.origin;
  const manifest = origin?.manifest ?? endpoint?.manifest;
  const implementation = origin?.implementation ?? endpoint?.implementation;
  const loading = setup.isPending || endpoints.isPending;
  const loadError = (registrationId ? endpoints.error : setup.error)?.message;

  const run: RunAction = async action => {
    setBusy(true);
    setNotice(null);
    try {
      const message = await action();
      if (message) setNotice({ severity: "success", text: message });
      await client.invalidateQueries({ queryKey: ["admin"] });
    } catch (error) {
      setNotice({ severity: "error", text: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const check = (descriptor: boolean) => void run(async () => {
    if (!endpoint) return;
    const result = await checkProcessorEndpoint(endpoint.id, descriptor);
    if (!result.ok) throw new Error(result.detail);
    return descriptor ? "Processor descriptor verified." : "Processor is reachable.";
  });

  return <Stack spacing={2} sx={{ maxWidth: 780, mx: "auto" }}>
    <Button component={Link} to={SETUP_PATH + "#processors-heading"} startIcon={<ArrowBackIcon />} sx={{ alignSelf: "start" }}>Setup</Button>
    {loading && !name && <LinearProgress aria-label="Loading processor" />}
    {!loading && !name && <Alert severity={loadError ? "error" : "warning"}>{loadError ?? "This processor is no longer listed in Setup."}</Alert>}
    {name && <>
      <Stack component="header" spacing={0.5}>
        <Stack direction="row" alignItems="center" flexWrap="wrap" useFlexGap spacing={1}>
          <Typography variant="h5" component="h1" fontWeight={700}>{name}</Typography>
          <IconButton size="small" aria-label="About this processor" onClick={() => setHelp(true)}><HelpOutlineIcon fontSize="small" /></IconButton>
          {endpoint?.enabled === false ? <Chip label="Disabled" size="small" /> : item &&
            <Chip size="small" variant="outlined" color={item.available ? "success" : "default"} label={item.available ? "Available" : "Unavailable"} />}
        </Stack>
        {(item?.description || endpoint?.description) && <Typography color="text.secondary">{item?.description ?? endpoint?.description}</Typography>}
      </Stack>
      {notice && <Alert severity={notice.severity} onClose={() => setNotice(null)} sx={{ overflowWrap: "anywhere" }}>{notice.text}</Alert>}
      {settings.isError && <Alert severity="error">{settings.error.message}</Alert>}
      {Object.keys(properties).length > 0 && settings.data &&
        <RuntimeSettings key={id} id={id} saved={settings.data.settings[id] ?? emptySettings} properties={properties} busy={busy} run={run} />}
      {endpoint && <EndpointSettings key={JSON.stringify([endpoint.id, endpoint.base_url, endpoint.model_access?.bindings])} endpoint={endpoint}
        providers={providers.data?.providers ?? []} busy={busy} run={run} />}
      {!endpoint && address && <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{address}</Typography>}
      <ProcessorStartupSettings key={id} processorId={id} />
      <Paper component="section" variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1}>
          <Typography variant="h6" component="h2">Status</Typography>
          {item?.detail && <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{item.detail}</Typography>}
          {endpoint?.enabled && <Stack direction="row" spacing={1}>
            <Button disabled={busy} onClick={() => check(false)}>Check health</Button>
            <Button disabled={busy} onClick={() => check(true)}>Check descriptor</Button>
          </Stack>}
          {service && <><Divider /><ServiceRow service={service} busy={busy}
            onAction={action => void run(async () => { await controlCapabilityService(service.id, action); })}
            onLogs={setup.data?.service_control_available ? () => void run(async () => {
              const result = await getCapabilityServiceLogs(service.id);
              setLogs(result.lines);
            }) : undefined} /></>}
          {endpoint?.enabled && <Button color="error" size="small" disabled={busy} onClick={() => setConfirmRemove(true)} sx={{ alignSelf: "start" }}>
            {removalAction} registration
          </Button>}
          {endpoint?.built_in && !endpoint.enabled && <Button size="small" disabled={busy} sx={{ alignSelf: "start" }}
            onClick={() => void run(async () => {
              await updateProcessorEndpoint(endpoint.id, { enabled: true, preserve_processor: true });
              return "Processor enabled.";
            })}>Enable registration</Button>}
        </Stack>
      </Paper>
    </>}
    <Dialog open={help} onClose={() => setHelp(false)} fullWidth maxWidth="sm">
      <DialogTitle>About this processor</DialogTitle>
      <DialogContent><Stack spacing={1} sx={{ overflowWrap: "anywhere" }}>
        <Typography variant="body2">Processor <code>{id}</code></Typography>
        {implementation && <Typography variant="body2">Implementation <code>{implementation}</code></Typography>}
        {manifest && <Typography variant="body2">Module manifest <code>{manifest}</code></Typography>}
        {origin?.configuration_file && <Typography variant="body2">Configuration <code>{origin.configuration_file}</code></Typography>}
        <Typography variant="body2">Use <strong>Processing flows</strong> in Setup to control which processors run and in what order.</Typography>
      </Stack></DialogContent>
      <DialogActions><Button onClick={() => setHelp(false)}>Close</Button></DialogActions>
    </Dialog>
    <Dialog open={logs !== null} onClose={() => setLogs(null)} fullWidth maxWidth="md">
      <DialogTitle>Service logs</DialogTitle>
      <DialogContent><Box component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{logs?.join("\n") || "No logs available."}</Box></DialogContent>
      <DialogActions><Button onClick={() => setLogs(null)}>Close</Button></DialogActions>
    </Dialog>
    <Dialog open={confirmRemove} onClose={() => setConfirmRemove(false)}>
      <DialogTitle>{removalAction} {name}?</DialogTitle>
      <DialogContent>Processing flows that use this registration will need a replacement.</DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setConfirmRemove(false)}>Cancel</Button>
        <Button disabled={busy} color="error" onClick={() => {
          setConfirmRemove(false);
          if (endpoint) void run(async () => {
            await deleteProcessorEndpoint(endpoint.id);
            if (!endpoint.built_in) navigate(SETUP_PATH);
            else return "Processor disabled.";
          });
        }}>{removalAction}</Button>
      </DialogActions>
    </Dialog>
  </Stack>;
}
