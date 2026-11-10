import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Stack,
  Tab,
  Tabs,
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
    <Stack spacing={2.5} sx={{ maxWidth: 1100, mx: "auto" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight={750}>
          Setup
        </Typography>
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
            : onSection(
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
      <Tabs
        value={section}
        onChange={(_, value: SetupSection) => onSection(value)}
        variant="scrollable"
        allowScrollButtonsMobile
        aria-label="Setup sections"
      >
        <Tab
          value="models"
          label="Model connections"
          id="setup-models"
          aria-controls="setup-panel-models"
        />
        <Tab
          value="source"
          label="Source folder"
          id="setup-source"
          aria-controls="setup-panel-source"
        />
        <Tab
          value="processors"
          label="Processing methods"
          id="setup-processors"
          aria-controls="setup-panel-processors"
        />
      </Tabs>
      <Box
        role="tabpanel"
        id={`setup-panel-${section}`}
        aria-labelledby={`setup-${section}`}
      >
        {section === "models" && (
          <ModelAdmin embedded onChanged={() => setRevision((v) => v + 1)} />
        )}
        {section === "source" && (
          <SourceAdmin embedded onChanged={() => setRevision((v) => v + 1)} />
        )}
        {section === "processors" && (
          <ProcessorAdmin
            embedded
            queue={queue}
            onChanged={() => setRevision((v) => v + 1)}
          />
        )}
      </Box>
      {failed && !data && (
        <Alert severity="info">
          Source and connection controls remain available. Refresh readiness
          after resolving the service error.
        </Alert>
      )}
    </Stack>
  );
}
