import { ServiceAdmin } from "./ServiceAdmin";
import { ExpandMore } from "@mui/icons-material";
import { CapabilitySection, SetupLayout, type CapabilityKind } from "../admin/components/SetupLayout";
import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Stack,
  Accordion, AccordionSummary, AccordionDetails,
  Typography,
} from "@mui/material";
import { ReadinessPanel } from "../../components/discovery/ReadinessPanel";
import { api } from "./api";
import { ModelAdmin, type Configuration } from "./ModelAdmin";
import { ProcessorAdmin, type ProcessorStatus } from "./ProcessorAdmin";
import { SourceAdmin, type SourceStatus } from "./SourceAdmin";

export type SetupSection = "models" | "source" | "processors";
export function Setup({
  section,
  onSection,
  queue,
  onProcessing,
}: {
  section: SetupSection;
  onSection: (section: SetupSection) => void;
  queue: (processor: ProcessorStatus) => void;
  onProcessing: () => void;
}) {
  const [data, setData] = useState<{
    source: SourceStatus;
    models: Configuration;
    processors: ProcessorStatus[];
  } | null>(null);
  const [checking, setChecking] = useState(true);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const [expanded, setExpanded] = useState<CapabilityKind | false>(false);
  const [sourceOpen, setSourceOpen] = useState(section === "source");
  useEffect(() => {
    if (section === "source") setSourceOpen(true);
    if (section === "processors") setExpanded("extractor");
    if (section === "models") return;
    const timer = window.setTimeout(() => document.getElementById(`setup-${section}`)?.scrollIntoView({ block: "start" }), 0);
    return () => window.clearTimeout(timer);
  }, [section]);
  const followSection = (value: SetupSection) => {
    onSection(value);
    if (value === "source") setSourceOpen(true);
    if (value === "processors") setExpanded("extractor");
    window.setTimeout(() => document.getElementById(`setup-${value}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };
  useEffect(() => {
    let current = true;
    const refresh = async () => {
      setChecking(true);
      try {
        const [source, models, processors] = await Promise.all([
          api<SourceStatus>("/api/admin/source"),
          api<Configuration>("/api/admin/models"),
          api<{ processors: ProcessorStatus[] }>("/api/admin/processors"),
        ]);
        if (current) {
          setData({ source, models, processors: processors.processors });
          setFailed(false);
        }
      } catch {
        if (current) setFailed(true);
      } finally {
        if (current) setChecking(false);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [revision]);
  const count = data?.source.statistics.documents ?? 0;
  const text = data?.source.statistics.text_documents ?? 0;
  const indexed = data?.source.statistics.indexed_documents ?? 0;
  const configured = (kind: "chat" | "embedding") =>
    Boolean(
      data?.models.endpoints[kind].configured &&
        data.models.endpoints[kind].model,
    );
  const steps = [
    {
      id: "source",
      label: "Source folder",
      complete: Boolean(data?.source.available && data.source.readable),
      detail:
        data?.source.directory || "Choose a folder on the mounted source.",
    },
    {
      id: "extractor",
      label: "Document reader",
      complete: Boolean(
        data?.processors.some((p) => p.kind === "extractor" && p.available),
      ),
      detail: "Check configured document readers and optional OCR services.",
    },
    {
      id: "embedding",
      label: "Embedding model",
      complete: configured("embedding"),
      statusLabel: configured("embedding")
        ? "selected; sample test is manual"
        : undefined,
      detail:
        "Select an embedding connection. Use its sample test to verify reachability.",
    },
    {
      id: "language",
      label: "Language model",
      complete: configured("chat"),
      statusLabel: configured("chat")
        ? "selected; sample test is manual"
        : undefined,
      detail:
        "Select a language connection. Use its sample test to verify reachability.",
    },
    {
      id: "text",
      label: "Documents read",
      complete: count > 0 && text === count,
      detail: `${text} of ${count} documents have saved text.`,
    },
    {
      id: "index",
      label: "Semantic index",
      complete: count > 0 && indexed === count && configured("embedding"),
      detail: `${indexed} of ${count} documents have vectors on every chunk for the selected model.`,
    },
  ];
  return (
    <SetupLayout>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography color="text.secondary">Connect models, choose processing methods, then continue to Intake.</Typography>
        <Button disabled={checking} onClick={() => setRevision((v) => v + 1)}>
          Refresh readiness
        </Button>
      </Stack>
      <ReadinessPanel
        steps={steps}
        loading={checking && !data}
        failed={failed}
        hasPrevious={Boolean(data)}
        completionLabel="prepared"
        onStep={(id) =>
          id === "text" || id === "index"
            ? onProcessing()
            : followSection(
                id === "source"
                  ? "source"
                  : id === "extractor"
                    ? "processors"
                    : "models",
              )
        }
      />
      <Typography variant="caption" color="text.secondary">
        Model checkpoints show saved selections. Sample tests verify the
        services and run only when requested; browsing and keyword search work
        without models.
      </Typography>
      <ServiceAdmin />
      <Box id="setup-models" sx={{ scrollMarginTop: 80 }}>
        <ModelAdmin embedded onChanged={() => setRevision(v => v + 1)} />
      </Box>
      <Stack spacing={1.25} id="setup-processors" sx={{ scrollMarginTop: 80 }}>
        <Typography variant="h6" fontWeight={700}>Processing defaults</Typography>
        {(["extractor", "synthesizer", "embedder", "enricher"] as CapabilityKind[]).map(kind => {
          const methods = data?.processors.filter(p => p.kind === kind) ?? [];
          const available = kind === "embedder" ? Number(configured("embedding")) : methods.filter(p => p.available).length;
          const summary = !data ? "Checking configured methods…" : kind === "embedder"
            ? configured("embedding") ? data.models.endpoints.embedding.model : "Connect an embedding model · keyword search remains available"
            : `${methods.length} configured · ${available} available`;
          return <CapabilitySection key={kind} kind={kind} expanded={expanded === kind}
            onChange={open => setExpanded(open ? kind : false)} summary={summary} available={data ? available : undefined} countLabel={kind === "embedder" ? "configured" : "available"}>
            {kind === "embedder" ? <Stack spacing={1}>
              <Typography>Embedding configuration is shown above in Model connections. Selecting a model does not test its connection.</Typography>
              <Button onClick={() => followSection("models")} sx={{ alignSelf: "start" }}>Configure embedding model</Button>
              <Button onClick={onProcessing} sx={{ alignSelf: "start" }}>Queue embeddings in Intake</Button>
            </Stack> : <ProcessorAdmin embedded kind={kind} queue={queue} onChanged={() => setRevision(v => v + 1)} />}
            {kind !== "embedder" && data && !methods.length && <Typography color="text.secondary">No configured methods. Register a running Processor API service under Advanced &amp; diagnostics.</Typography>}
          </CapabilitySection>;
        })}
      </Stack>
      <Accordion slotProps={{ transition: { unmountOnExit: true } }} id="setup-source" expanded={sourceOpen} onChange={(_, open) => setSourceOpen(open)} variant="outlined" disableGutters sx={{ scrollMarginTop: 80, borderRadius: "12px !important" }}>
        <AccordionSummary expandIcon={<ExpandMore />}><Typography fontWeight={700}>Source folder</Typography></AccordionSummary>
        <AccordionDetails><SourceAdmin embedded onChanged={() => setRevision(v => v + 1)} /></AccordionDetails>
      </Accordion>
      <Accordion slotProps={{ transition: { unmountOnExit: true } }} variant="outlined" disableGutters sx={{ borderRadius: "12px !important" }}>
        <AccordionSummary expandIcon={<ExpandMore />}><Typography fontWeight={700}>Advanced &amp; diagnostics</Typography></AccordionSummary>
        <AccordionDetails><Stack spacing={2}>
          <Typography color="text.secondary">Inspect service health and register optional Toolbox connections. Services are deployed and restarted by the server operator; registering an address does not start a service.</Typography>
          <ProcessorAdmin embedded queue={queue} onChanged={() => setRevision(v => v + 1)} />
        </Stack></AccordionDetails>
      </Accordion>
      <Button variant="contained" color="secondary" onClick={onProcessing} sx={{ alignSelf: "end" }}>Continue to Intake →</Button>
      {failed && !data && (
        <Alert severity="info">
          Source and connection controls remain available. Refresh readiness
          after resolving the service error.
        </Alert>
      )}
    </SetupLayout>
  );
}
