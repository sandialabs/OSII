import { useEffect, useRef, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DiscoveryIntakePanel } from "../queue/components/DiscoveryIntakePanel";
import { DiscoveryActivity } from "../queue/components/DiscoveryActivity";
import type { PickedFile } from "../../components/discovery/LocationBrowser";
import { useQuery } from "@tanstack/react-query";
import { FileSelectionList } from "../queue/components/FileSelectionList";
import {
  IntakeSections,
  type IntakeSection,
} from "../queue/components/IntakeSections";
import { ProcessorStepControl } from "../queue/components/ProcessorStepControl";
import { ProcessorConfigInput } from "../queue/components/ProcessorConfigInput";
import type { ProcessorConfigSchema } from "../../api/types";
import {
  ProcessingActivity,
  type ProcessingAction,
} from "../queue/components/ProcessingActivity";
import type { ProcessingRun } from "../../api/types";
import type { ProcessorStatus } from "./ProcessorAdmin";
import ExpandMoreOutlined from "@mui/icons-material/ExpandMoreOutlined";
import { api, type Doc } from "./api";

type Processor = {
  id: string;
  display_name: string;
  kind: string;
  available: boolean;
  detail: string;
  model_requirements: Record<string, string>;
  descriptor: { config_schema?: ProcessorConfigSchema; capabilities?: { scope_types: string[] } };
};
type Plan = {
  synthesis_calls_estimate?: number;
  items: { path: string; size_bytes: number; indexed: boolean }[];
  embedding_model: string;
  embedding_model_name?: string;
};
export function Intake({
  initialPaths = [],
  initialProcessor = null,
  initialSection = "add",
}: {
  initialPaths?: string[];
  initialProcessor?: ProcessorStatus | null;
  initialSection?: IntakeSection;
}) {
  const [section, setSection] = useState<IntakeSection>(
    initialPaths.length || initialProcessor ? "process" : initialSection,
  );
  const [selectionId, setSelectionId] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(window.location.search).get("selection"));
    return Number.isSafeInteger(id) && id > 0 ? id : null;
  });
  const [directFiles, setDirectFiles] = useState<PickedFile[]>(initialPaths.map(path => ({ path, name: path.split("/").pop() ?? path, size_bytes: null })));
  const capabilities = useQuery({ queryKey: ["discovery", "capabilities"], queryFn: () => api<{ mount_root: string }>("/api/volume/capabilities") });
  const [docs, setDocs] = useState<Doc[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [paths, setPaths] = useState<string[]>(initialPaths);
  const [operation, setOperation] = useState(
    initialProcessor?.kind === "extractor"
      ? "reprocess"
      : initialPaths.length || initialSection === "process" || initialProcessor
        ? "process"
        : "missing",
  );
  const [processors, setProcessors] = useState<Processor[]>([]);
  const [urls, setUrls] = useState("");
  const [extractor, setExtractor] = useState(
    initialProcessor?.kind === "extractor" ? initialProcessor.id : "",
  );
  const [extractConfig, setExtractConfig] = useState<Record<string, unknown>>(
    {},
  );
  const [extractionPolicy, setExtractionPolicy] = useState("make_primary");
  const [synthesize, setSynthesize] = useState(
    initialProcessor?.kind === "synthesizer",
  );
  const [enrich, setEnrich] = useState(initialProcessor?.kind === "enricher");
  const [synthesizer, setSynthesizer] = useState(
    initialProcessor?.kind === "synthesizer"
      ? initialProcessor.id
      : "local.extractive-preview",
  );
  const [enricher, setEnricher] = useState(
    initialProcessor?.kind === "enricher"
      ? initialProcessor.id
      : "local.stats-keywords",
  );
  const [synthConfig, setSynthConfig] = useState<Record<string, unknown>>({});
  const [enrichConfig, setEnrichConfig] = useState<Record<string, unknown>>({});
  const [expertContext, setExpertContext] = useState("");
  const [embed, setEmbed] = useState(false);
  const [excludedPaths, setExcludedPaths] = useState<string[]>([]);
  const [preview, setPreview] = useState<Plan | null>(null);
  const [runs, setRuns] = useState<ProcessingRun[]>([]);
  const [workerAvailable, setWorkerAvailable] = useState<boolean>();
  const [selectedLogRunId, setSelectedLogRunId] = useState<string | null>(null);
  const [controlling, setControlling] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [goal, setGoal] = useState(
    initialProcessor?.kind === "extractor"
      ? "reextract"
      : initialProcessor?.kind === "synthesizer"
        ? "synthesize"
        : initialProcessor?.kind === "enricher"
          ? "enrich"
          : "custom",
  );
  const [preset, setPreset] = useState("text");
  const revision = useRef(0);
  const refreshProcessors = async () => {
    const result = await api<{ processors: Processor[]; urls: string[] }>(
      "/api/admin/processors",
    );
    setProcessors(result.processors);
    setUrls(result.urls.join("\n"));
  };
  const saveProcessors = async () => {
    setBusy(true);
    setError("");
    invalidate();
    try {
      await api("/api/admin/processors", "PUT", {
        urls: urls
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
      });
      await refreshProcessors();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  const refresh = async () => {
    const r = await api<{
      runs: ProcessingRun[];
      worker: { available: boolean };
    }>("/api/admin/runs");
    setRuns(r.runs);
    setWorkerAvailable(r.worker.available);
    setSelectedLogRunId((id) => id ?? r.runs[0]?.id ?? null);
  };
  const loadDocs = async (cursor?: string) => {
    const r = await api<{ items: Doc[]; next_cursor: string | null }>(
      `/api/catalog/files?limit=500${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    );
    setDocs((current) => (cursor ? [...current, ...r.items] : r.items));
    setNextCursor(r.next_cursor);
  };
  const fail = (e: unknown) => setError((e as Error).message);
  useEffect(() => {
    void refreshProcessors().catch(fail);
    void loadDocs().catch(fail);
    void refresh().catch(fail);
    const timer = window.setInterval(() => void refresh().catch(fail), 2500);
    return () => window.clearInterval(timer);
  }, []);
  const invalidate = () => {
    revision.current += 1;
    setPreview(null);
    setExcludedPaths([]);
    setError("");
  };
  const toggle = (path: string) => {
    invalidate();
    setPaths((current) =>
      current.includes(path)
        ? current.filter((p) => p !== path)
        : [...current, path],
    );
  };
  const derivedSettings = () => ({
    extractor_name: extractor || null,
    extractor_config: extractConfig,
    extraction_policy: extractionPolicy,
    synthesizer_name: synthesize ? synthesizer : null,
    enricher_name: enrich ? enricher : null,
    synthesizer_config: synthConfig,
    enricher_config: enrichConfig,
    expert_context: expertContext,
  });
  const configFields = (
    name: string,
    config: Record<string, unknown>,
    update: (config: Record<string, unknown>) => void,
  ) =>
    Object.entries(
      processors.find((p) => p.id === name)?.descriptor.config_schema
        ?.properties ?? {},
    ).map(([key, property]) => (
      <ProcessorConfigInput
        key={key}
        name={key}
        property={property}
        value={config[key] ?? property.default ?? ""}
        onChange={(value) => {
          invalidate();
          update({ ...config, [key]: value });
        }}
      />
    ));
  const inspect = async () => {
    const current = revision.current;
    setBusy(true);
    setError("");
    try {
      const result = await api<Plan>("/api/admin/inventory/intake/preview", "POST", {
        ...(selectionId !== null && section === "add" ? { selection_id: selectionId } : { paths }),
        operation,
        embed,
        ...derivedSettings(),
      });
      if (current === revision.current) setPreview(result);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  const stage = async () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      // Freeze the exact previewed files, rather than silently including new files in a folder.
      const run = await api<ProcessingRun>("/api/admin/inventory/intake/stage", "POST", {
        ...(selectionId !== null && section === "add" ? { selection_id: selectionId, excluded_paths: excludedPaths } : { paths: preview.items.filter((item) => !excludedPaths.includes(item.path)).map((item) => item.path) }),
        operation,
        embed,
        ...derivedSettings(),
      });
      setSelectedLogRunId(run.id);
      setSection("activity");
      setPaths([]);
      invalidate();
      setNotice(
        "Plan staged. Review its files below, then choose Start processing. No processing has started yet.",
      );
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  const control = async (run: ProcessingRun, action: ProcessingAction) => {
    setControlling(`${run.id}:${action}`);
    setError("");
    try {
      await api(`/api/admin/runs/${run.id}/${action}`, "POST", {});
      await refresh();
      setNotice(
        action === "pause" || action === "cancel"
          ? "Request saved. A running file finishes safely before the worker stops this run."
          : "Run queued. Completed files will not be repeated.",
      );
    } catch (e) {
      fail(e);
    } finally {
      setControlling(null);
    }
  };
  const chooseWork = (value: string) => {
    invalidate();
    setGoal(value);
    setExtractionPolicy("make_primary");
    if (value === "custom") return;
    setOperation(
      value === "reextract"
        ? "reprocess"
        : value === "embed"
          ? "embed"
          : "process",
    );
    setEmbed(value === "embed");
    setSynthesize(value === "synthesize");
    setEnrich(value === "enrich");
  };
  const selectedRun = runs.find((run) => run.id === selectedLogRunId);
  return (
    <Stack spacing={2.5} sx={{ maxWidth: 1100, mx: "auto" }}>
      <Box>
        <Typography variant="h5" fontWeight={700}>
          Intake
        </Typography>
        <Typography color="text.secondary">
          Select files, review a plan, then start it. Originals on the mounted
          share stay read-only.
        </Typography>
      </Box>
      {error && (
        <Alert severity="error" onClose={() => setError("")}>
          {error}
        </Alert>
      )}
      {notice && (
        <Alert severity="info" onClose={() => setNotice("")}>
          {notice}
        </Alert>
      )}
      <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
        <IntakeSections
          value={section}
          onChange={(value) => {
            setSection(value);
            if (value !== "activity") {
              setPaths([]);
              setDirectFiles([]);
              setSelectionId(null);
              invalidate();
            }
          }}
        />
      </Box>
      {section !== "activity" && (
        <>
          {section === "process" && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stack spacing={1.5}>
                <Typography variant="h6" component="h2" fontWeight={750}>
                  1. Choose work
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {[
                    ["embed", "Add embeddings"],
                    ["synthesize", "Generate summaries"],
                    ["reextract", "Upgrade extraction"],
                    ["enrich", "Run enrichment"],
                    ["custom", "Custom workflow"],
                  ].map(([value, label]) => (
                    <Button
                      key={value}
                      color="secondary"
                      variant={goal === value ? "contained" : "outlined"}
                      onClick={() => chooseWork(value)}
                    >
                      {label}
                    </Button>
                  ))}
                </Stack>
                {goal === "reextract" && (
                  <Alert severity="info">
                    Previous extractions are kept. Choose whether the new
                    version becomes primary.
                  </Alert>
                )}
              </Stack>
            </Paper>
          )}
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={1.5}>
              <Typography variant="h6" component="h2" fontWeight={750}>
                {section === "add" ? "1. Choose files" : "2. Select documents"}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {selectionId !== null && section === "add" ? `Frozen inventory batch #${selectionId}. Preview it below before staging.` : `${paths.length} selected files. Preview and review the exact files before staging.`}
              </Typography>
              {section === "add" ? (
                <DiscoveryIntakePanel
                  selectedId={selectionId}
                  onSelect={(id) => { invalidate(); setSelectionId(id); }}
                  directFiles={directFiles}
                  onFiles={(files) => { invalidate(); setDirectFiles(files); setPaths(files.map(file => file.path)); }}
                  allowUploads={false}
                  boundaryPath={capabilities.data?.mount_root}
                />
              ) : (
                <>
                  <Button
                    color="secondary"
                    onClick={() => {
                      invalidate();
                      setPaths(docs.map((doc) => doc.source_relpath));
                    }}
                  >
                    Select all loaded documents ({docs.length})
                  </Button>
                  <Box sx={{ maxHeight: 360, overflow: "auto" }}>
                    {docs.map((doc) => (
                      <FormControlLabel
                        key={doc.file_id}
                        sx={{ display: "flex" }}
                        control={
                          <Checkbox
                            checked={paths.includes(doc.source_relpath)}
                            onChange={() => toggle(doc.source_relpath)}
                          />
                        }
                        label={doc.source_relpath}
                      />
                    ))}
                  </Box>
                  {nextCursor && (
                    <Button
                      color="secondary"
                      onClick={() => void loadDocs(nextCursor).catch(fail)}
                    >
                      Load more documents
                    </Button>
                  )}
                </>
              )}
              <Button
                color="secondary"
                disabled={!paths.length && selectionId === null}
                onClick={() => {
                  invalidate();
                  setPaths([]);
                }}
              >
                Clear selection
              </Button>
            </Stack>
          </Paper>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={2}>
              <Typography variant="h6" component="h2" fontWeight={750}>
                {section === "add"
                  ? "2. Review and process batch"
                  : "3. Review and stage processing"}
              </Typography>
              {section === "add" && (
                <TextField
                  select
                  size="small"
                  label="Processing preset"
                  value={preset}
                  onChange={(event) => {
                    const value = event.target.value;
                    invalidate();
                    setPreset(value);
                    setOperation("missing");
                    setExtractionPolicy("make_primary");
                    setEmbed(value === "summary-search");
                    setSynthesize(value === "summary-search");
                    setEnrich(false);
                  }}
                >
                  <MenuItem value="text">
                    Read documents · keyword search
                  </MenuItem>
                  <MenuItem value="summary-search">
                    Read, summarize and embed
                  </MenuItem>
                </TextField>
              )}
              <Accordion variant="outlined" disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
                  <Stack>
                    <Typography fontWeight={700}>Processing options</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {operation === "embed"
                        ? "Re-embed existing text"
                        : operation === "process"
                          ? "Use existing text"
                          : operation === "reprocess"
                            ? "Re-extract selected files"
                            : "Read new or changed files"}
                      {embed || operation === "embed" ? " · embeddings" : ""}
                      {synthesize ? " · summaries" : ""}
                      {enrich ? " · enrichment" : ""}
                    </Typography>
                  </Stack>
                </AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={2}>
                    <TextField
                      select
                      label="Work to perform"
                      value={operation}
                      onChange={(e) => {
                        invalidate();
                        setOperation(e.target.value);
                        setExtractionPolicy("make_primary");
                      }}
                    >
                      <MenuItem value="missing">
                        Intake / refresh changed files
                      </MenuItem>
                      <MenuItem value="reprocess">
                        Re-extract all selected files
                      </MenuItem>
                      <MenuItem value="embed">Re-embed existing text</MenuItem>
                      <MenuItem value="process">
                        Process existing text without extraction
                      </MenuItem>
                    </TextField>
                    {!["process", "embed"].includes(operation) && (
                      <Stack spacing={1}>
                        <TextField
                          select
                          label="Extractor"
                          value={
                            processors.some((p) => p.id === extractor)
                              ? extractor
                              : ""
                          }
                          onChange={(e) => {
                            invalidate();
                            setExtractor(e.target.value);
                            setExtractConfig({});
                          }}
                        >
                          <MenuItem value="">
                            Deployment default (native text, then configured OCR
                            fallback)
                          </MenuItem>
                          {processors
                            .filter((p) => p.kind === "extractor")
                            .map((p) => (
                              <MenuItem
                                key={p.id}
                                value={p.id}
                                disabled={!p.available}
                              >
                                {p.display_name}
                                {!p.available ? " — unavailable" : ""}
                              </MenuItem>
                            ))}
                        </TextField>
                        {extractor &&
                          configFields(
                            extractor,
                            extractConfig,
                            setExtractConfig,
                          )}
                        <TextField
                          select
                          label="After extraction"
                          value={extractionPolicy}
                          onChange={(e) => {
                            invalidate();
                            setExtractionPolicy(e.target.value);
                            if (e.target.value === "save_variant") {
                              setSynthesize(false);
                              setEnrich(false);
                              setEmbed(false);
                            }
                          }}
                        >
                          <MenuItem value="make_primary">
                            Make primary; preserve previous extractions
                          </MenuItem>
                          <MenuItem value="save_variant">
                            Save another version; keep current primary and
                            search text
                          </MenuItem>
                        </TextField>
                        <Typography variant="caption">
                          Use Re-extract all selected files to compare OCR with
                          an existing text layer. Saved variants appear in the
                          document's Extractions and representation selector.
                        </Typography>
                      </Stack>
                    )}
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={embed || operation === "embed"}
                          disabled={
                            operation === "embed" ||
                            extractionPolicy === "save_variant"
                          }
                          onChange={(e) => {
                            invalidate();
                            setEmbed(e.target.checked);
                          }}
                        />
                      }
                      label="Build embeddings using the selected embedding model"
                    />
                    <Typography variant="body2" color="text.secondary">
                      Text-only processing supports keyword search without a
                      model. Embedding requests may use provider credit.
                      Synthesis and enrichment create separate derived outputs;
                      extracted text stays unchanged. Model-backed methods may
                      use provider credit.
                    </Typography>
                    <ProcessorStepControl
                      disabled={extractionPolicy === "save_variant"}
                      label="Generate document summaries"
                      methodLabel="Synthesizer"
                      checked={synthesize}
                      onChecked={(value) => {
                        invalidate();
                        setSynthesize(value);
                      }}
                      method={synthesizer}
                      onMethod={(value) => {
                        invalidate();
                        setSynthesizer(value);
                        setSynthConfig({});
                      }}
                      options={processors.filter(
                        (p) => p.kind === "synthesizer" && p.descriptor.capabilities?.scope_types.includes("object"),
                      )}
                      helperText={
                        synthesizer === "local.extractive-preview"
                          ? "No AI: cited source excerpts, without generating new prose."
                          : "Uses the selected language model or configured Processor API service."
                      }
                    >
                      {configFields(synthesizer, synthConfig, setSynthConfig)}
                    </ProcessorStepControl>
                    <ProcessorStepControl
                      disabled={extractionPolicy === "save_variant"}
                      label="Run enrichment"
                      methodLabel="Enricher"
                      checked={enrich}
                      onChecked={(value) => {
                        invalidate();
                        setEnrich(value);
                      }}
                      method={enricher}
                      onMethod={(value) => {
                        invalidate();
                        setEnricher(value);
                        setEnrichConfig({});
                      }}
                      options={processors.filter((p) => p.kind === "enricher" && p.descriptor.capabilities?.scope_types.includes("object"))}
                      helperText="The built-in statistics/keywords method is deterministic and needs no model. External processor methods remain optional."
                    >
                      {configFields(enricher, enrichConfig, setEnrichConfig)}
                    </ProcessorStepControl>
                    <TextField
                      label="Expert context (optional)"
                      value={expertContext}
                      multiline
                      minRows={2}
                      inputProps={{ maxLength: 8000 }}
                      onChange={(e) => {
                        invalidate();
                        setExpertContext(e.target.value);
                      }}
                      helperText="Additional guidance supplied to the selected processors; it is recorded with their outputs."
                    />
                    <Box component="details">
                      <Typography
                        component="summary"
                        sx={{ cursor: "pointer" }}
                      >
                        Processor connections
                      </Typography>
                      <Stack spacing={1} sx={{ mt: 1 }}>
                        <Typography variant="body2">
                          Baseline methods work without another service. Add
                          explicitly deployed Processor API base
                          addresses below, one per line. These are processor
                          services, not model-provider endpoints.
                        </Typography>
                        <TextField
                          multiline
                          minRows={2}
                          label="Processor API endpoints"
                          value={urls}
                          onChange={(e) => setUrls(e.target.value)}
                        />
                        <Button
                          color="secondary"
                          disabled={busy}
                          onClick={() => void saveProcessors()}
                        >
                          Save processor connections
                        </Button>
                        <Button
                          color="secondary"
                          onClick={() => void refreshProcessors().catch(fail)}
                        >
                          Refresh available methods
                        </Button>
                        {processors
                          .filter((p) => !p.available)
                          .map((p) => (
                            <Typography
                              key={p.id}
                              variant="caption"
                              color="text.secondary"
                            >
                              {p.display_name}: {p.detail}
                            </Typography>
                          ))}
                      </Stack>
                    </Box>
                  </Stack>
                </AccordionDetails>
              </Accordion>
              <Button
                color="secondary"
                variant="outlined"
                disabled={
                  busy ||
                  (!paths.length && !(selectionId !== null && section === "add")) ||
                  (operation === "process" && !synthesize && !enrich && !embed)
                }
                onClick={() => void inspect()}
              >
                {busy ? "Working…" : "Preview selected files"}
              </Button>
              {preview && (
                <>
                  <Typography fontWeight={700}>
                    {preview.items.length} files ·{" "}
                    {(
                      preview.items.reduce(
                        (sum, item) => sum + item.size_bytes,
                        0,
                      ) / 1048576
                    ).toFixed(1)}{" "}
                    MiB
                    {preview.embedding_model
                      ? ` · embedding model: ${preview.embedding_model_name || preview.embedding_model}`
                      : synthesize || enrich
                        ? " · no embeddings"
                        : " · text only"}
                  </Typography>
                  <Typography variant="body2">
                    {synthesize
                      ? `Synthesis: ${processors.find((p) => p.id === synthesizer)?.display_name || synthesizer}. `
                      : ""}
                    {enrich
                      ? `Enrichment: ${processors.find((p) => p.id === enricher)?.display_name || enricher}. `
                      : ""}
                  </Typography>
                  <Typography variant="body2">
                    {preview.synthesis_calls_estimate
                      ? `Approximately ${preview.synthesis_calls_estimate} synthesis model calls. Completed windows are saved for retry.`
                      : ""}
                  </Typography>
                  <Typography variant="body2">
                    Uncheck files to exclude them from the staged plan.
                  </Typography>
                  <FileSelectionList
                    files={preview.items}
                    excludedPaths={excludedPaths}
                    onToggle={(path) =>
                      setExcludedPaths((current) =>
                        current.includes(path)
                          ? current.filter((p) => p !== path)
                          : [...current, path],
                      )
                    }
                  />
                  <Button
                    color="secondary"
                    variant="contained"
                    disabled={
                      busy ||
                      preview.items.every((item) =>
                        excludedPaths.includes(item.path),
                      )
                    }
                    onClick={() => void stage()}
                  >
                    Stage plan — do not start yet
                  </Button>
                </>
              )}
            </Stack>
          </Paper>
        </>
      )}
      {section === "activity" && (
        <Stack spacing={2}><DiscoveryActivity /><ProcessingActivity
          recentRuns={runs}
          workerAvailable={workerAvailable}
          selectedLogRunId={selectedLogRunId}
          setSelectedLogRunId={setSelectedLogRunId}
          controllingRun={controlling}
          controlRun={control}
          displayedLogLines={selectedRun?.logs ?? []}
          refreshLogs={() => void refresh().catch(fail)}
          onRestage={(run) => {
            const failed = (run.items ?? [])
              .filter((item) => item.status === "error")
              .map((item) => item.display);
            if (!failed.length) {
              setError(
                "This older run has no file checkpoints. Select its source files under Add files.",
              );
              return;
            }
            setPaths(failed);
            setSection("add");
            setOperation("reprocess");
            invalidate();
            setNotice(
              "Failed files selected. Review the extractor, methods and settings, then preview and stage a new plan.",
            );
          }}
        /></Stack>
      )}
    </Stack>
  );
}
