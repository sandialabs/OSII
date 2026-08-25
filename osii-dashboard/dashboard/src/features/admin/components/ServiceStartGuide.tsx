import { Alert, Box, Chip, Divider, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

import type { CapabilityReadiness, IntakeReadiness } from "../../../api/types";

type ServiceStartGuideProps = {
  readiness?: IntakeReadiness;
};

type StartedService = {
  name: string;
  purpose: string;
  address: string;
  capabilityId?: string;
};

const STARTED_SERVICES: StartedService[] = [
  {
    name: "OSII backend, worker, and grounded chat",
    purpose: "Intake, canonical .osii files, the catalog, BM25 keyword search, REST API, and chat fallbacks.",
    address: "http://127.0.0.1:8511",
  },
  {
    name: "Dashboard",
    purpose: "The web interface you are using now.",
    address: "http://127.0.0.1:5173",
  },
  {
    name: "Python text-layer PDF and Office extractor",
    purpose: "Reads text already inside PDFs, Office documents, RTF, and text/data files. It is not OCR.",
    address: "port 8092",
    capabilityId: "local.native-text",
  },
  {
    name: "Cited source-excerpt preview (no AI)",
    purpose: "Copies short passages from extracted text into cited Markdown. It does not interpret or rewrite the source.",
    address: "port 8093",
    capabilityId: "local.extractive-preview",
  },
  {
    name: "Lexical hashing vectors (no AI model)",
    purpose: "Maps tokens and adjacent word pairs into vectors. It finds shared wording, not semantic synonyms; BM25 remains available.",
    address: "port 8085",
    capabilityId: "local.hashing",
  },
  {
    name: "Document statistics and frequent keywords",
    purpose: "Deterministic Python counts and keyword tables built from extracted text.",
    address: "port 8094",
    capabilityId: "local.stats-keywords",
  },
  {
    name: "Noun/adjective phrase keywords and entity candidates",
    purpose: "Python enrichments that rank recurring 2–4 word phrases and find grounded capitalized names or acronyms. No AI model is called.",
    address: "inside OSII core",
  },
  {
    name: "Ollama, Shirty, and OpenAI HTTP adapter",
    purpose: "Connects OSII to model servers. The adapter is running, but it does not install, start, or contain Ollama or any model.",
    address: "port 8095",
  },
  {
    name: "MCP server for agents",
    purpose: "Lets compatible agents query the same OSII scopes and provenance as the dashboard.",
    address: "http://127.0.0.1:8022/mcp",
  },
];

function allCapabilities(readiness?: IntakeReadiness): CapabilityReadiness[] {
  if (!readiness) return [];
  return [
    ...readiness.extractors,
    ...readiness.synthesizers,
    ...readiness.embedders,
    ...readiness.enrichers,
  ];
}

function CommandPair({ mac, windows }: { mac: string; windows: string }) {
  return (
    <Box sx={{ bgcolor: "action.hover", borderRadius: 1, p: 1 }}>
      <Typography variant="caption" display="block"><strong>macOS/Linux:</strong> <code>{mac}</code></Typography>
      <Typography variant="caption" display="block"><strong>Windows PowerShell:</strong> <code>{windows}</code></Typography>
    </Box>
  );
}

function OptionalServiceCard({
  name,
  status,
  statusColor,
  children,
}: {
  name: string;
  status: string;
  statusColor: "success" | "warning" | "default";
  children: ReactNode;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 1.75, height: "100%" }}>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
          <Typography fontWeight={700}>{name}</Typography>
          <Chip size="small" color={statusColor} label={status} />
        </Stack>
        {children}
      </Stack>
    </Paper>
  );
}

export function ServiceStartGuide({ readiness }: ServiceStartGuideProps) {
  const capabilities = allCapabilities(readiness);
  const capability = (id: string) => capabilities.find((item) => item.id === id);
  const ollamaItems = capabilities.filter((item) => item.id.startsWith("ollama."));
  const ollamaReady = ollamaItems.some((item) => item.available);
  const ollamaDetected = ollamaItems.some((item) => item.detail.startsWith("Ollama is running"));
  const tesseractReady = capability("osii_tesseract")?.available ?? false;
  const tikaReady = capability("tika")?.available ?? false;

  return (
    <Stack spacing={2.5}>
      <Alert severity="success">
        <strong><code>make dev</code> started OSII itself.</strong> Everything in the first list below runs from this repository. Optional software such as Ollama and the Tesseract executable is deliberately not installed for you.
      </Alert>

      <Stack spacing={1}>
        <Typography variant="h6" fontWeight={700}>Running because you used <code>make dev</code></Typography>
        <Typography variant="body2" color="text.secondary">
          You do not need to start these again. The ports are shown so each process is identifiable rather than hidden behind “local service.”
        </Typography>
      </Stack>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" }, gap: 1.5 }}>
        {STARTED_SERVICES.map((service) => {
          const item = service.capabilityId ? capability(service.capabilityId) : undefined;
          const healthy = item?.available ?? true;
          return (
            <Paper key={service.name} variant="outlined" sx={{ p: 1.5 }}>
              <Stack spacing={0.75}>
                <Stack direction="row" spacing={1} justifyContent="space-between" alignItems="flex-start">
                  <Typography variant="body2" fontWeight={700}>{service.name}</Typography>
                  <Chip size="small" color={healthy ? "success" : "warning"} label={healthy ? "Running" : "Check service"} />
                </Stack>
                <Typography variant="body2">{service.purpose}</Typography>
                <Typography variant="caption" color="text.secondary">{service.address}</Typography>
              </Stack>
            </Paper>
          );
        })}
      </Box>

      <Divider />

      <Stack spacing={1}>
        <Typography variant="h6" fontWeight={700}>Optional software and services</Typography>
        <Typography variant="body2" color="text.secondary">
          Install or connect these only when you need the capability. Their absence does not prevent basic intake, browsing, BM25 search, or extractive chat.
        </Typography>
      </Stack>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" }, gap: 1.5 }}>
        <OptionalServiceCard
          name="Ollama models"
          status={ollamaReady ? "Model ready" : ollamaDetected ? "Running; model missing" : "Not detected"}
          statusColor={ollamaReady ? "success" : "default"}
        >
          <Typography variant="body2">
            <strong>OSII does not install or start Ollama.</strong> If you use it, manage the application separately, then return to <strong>AI models</strong> to check its configured URL and see installed models.
          </Typography>
          <Typography variant="caption" color="text.secondary">Used for semantic embeddings, generated synthesis, and model-backed chat. The CLI supports additional choices with <code>ollama list</code> and <code>ollama pull &lt;model&gt;</code>.</Typography>
        </OptionalServiceCard>

        <OptionalServiceCard name="Tesseract OCR for scanned PDFs" status={tesseractReady ? "Running" : "Install separately"} statusColor={tesseractReady ? "success" : "warning"}>
          <Typography variant="body2">
            <strong>The Tesseract executable is not bundled in the bare-metal workflow.</strong> Install Tesseract yourself and confirm <code>tesseract --version</code> works. Then start OSII&apos;s OpenCV/Tesseract wrapper:
          </Typography>
          <CommandPair mac="make dev-ocr-host" windows=".\\scripts\\osii.ps1 dev-ocr-host" />
          <Typography variant="caption" color="text.secondary">Produces OCR text and page-region bounding boxes at port 8080.</Typography>
        </OptionalServiceCard>

        <OptionalServiceCard name="Apache Tika extraction" status={tikaReady ? "Running" : "Optional container"} statusColor={tikaReady ? "success" : "default"}>
          <Typography variant="body2">
            Apache Tika is not started by <code>make dev</code>. In a second terminal, start only Tika below while keeping all editable OSII services on the host. Use <code>dev-containers</code> only when you also want containerized Tesseract OCR.
          </Typography>
          <CommandPair mac="make dev-tika" windows=".\\scripts\\osii.ps1 dev-tika" />
        </OptionalServiceCard>

        <OptionalServiceCard name="Corporate Shirty" status="Corporate endpoint" statusColor="default">
          <Typography variant="body2">
            Shirty is not local software. Set <code>SHIRTY_BASE_URL</code> and <code>SHIRTY_API_KEY</code>; OSII&apos;s bundled HTTP adapter then provides Shirty Textract, synthesis, and chat.
          </Typography>
          <CommandPair mac="make dev-corporate" windows=".\\scripts\\osii.ps1 dev-corporate" />
        </OptionalServiceCard>
      </Box>

      <Alert severity="info">
        To run just one bundled processor while developing it, use <code>make dev-extractor</code>, <code>make dev-synthesizer</code>, <code>make dev-embedder</code>, <code>make dev-enricher</code>, or the same command name with <code>.\\scripts\\osii.ps1</code> on Windows.
      </Alert>
    </Stack>
  );
}
