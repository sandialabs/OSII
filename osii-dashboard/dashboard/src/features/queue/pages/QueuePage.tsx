import {
  ChangeEvent,
  useDeferredValue,
  useMemo,
  useState,
} from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import AddOutlinedIcon from "@mui/icons-material/AddOutlined";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import PauseCircleOutlineOutlinedIcon from "@mui/icons-material/PauseCircleOutlineOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import {
  browseIntake,
  controlProcessingRun,
  createProcessingRun,
  getIntakeReadiness,
  listProcessingRuns,
  rescanSourcePaths,
  resolveIntake,
  uploadQueueFiles,
} from "../../../api/queue";
import type {
  QueueBrowseEntry,
  ProcessingRun,
  SourceRescanResponse,
  UploadResponse,
} from "../../../api/types";

type SelectedSharedItem = Pick<
  QueueBrowseEntry,
  "display" | "name" | "path" | "processed" | "type"
>;

type Notice = {
  severity: "error" | "info" | "success";
  text: string;
};

type ChunkingMethod = "sentence_window" | "paragraph" | "window";

const FILE_FILTERS = [
  { value: "all", label: "All file types", patterns: "" },
  {
    value: "documents",
    label: "Common documents",
    patterns: "*.pdf\n*.doc\n*.docx\n*.txt\n*.md\n*.rtf",
  },
  { value: "pdf", label: "PDF only", patterns: "*.pdf" },
  {
    value: "office",
    label: "Office documents",
    patterns: "*.doc\n*.docx\n*.xls\n*.xlsx\n*.ppt\n*.pptx",
  },
  {
    value: "text-data",
    label: "Text and tabular data",
    patterns: "*.txt\n*.md\n*.csv\n*.tsv\n*.json\n*.xml",
  },
  { value: "custom", label: "Custom patterns", patterns: "" },
] as const;

function formatSize(size: number | null | undefined): string {
  if (size == null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function secondsBetween(start?: string | null, end?: string | null): number | null {
  if (!start) return null;
  const startMs = Date.parse(start);
  const endMs = end ? Date.parse(end) : Date.now();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return null;
  return Math.max(0, (endMs - startMs) / 1000);
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "not recorded";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remainder}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function completedFileDurations(run: ProcessingRun): number[] {
  return (run.items ?? []).flatMap((item) => (
    typeof item.duration_seconds === "number" && Number.isFinite(item.duration_seconds)
      ? [item.duration_seconds]
      : []
  ));
}

function parentDisplay(display: string): string {
  const normalized = display.replace(/\\/g, "/");
  const parts = normalized.split("/");
  if (parts.length <= 1) return "Shared root";
  return parts.slice(0, -1).join("/");
}

export function QueuePage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [path, setPath] = useState("");
  const [includeSharedRoot, setIncludeSharedRoot] = useState(true);
  const [selectedSharedItems, setSelectedSharedItems] = useState<SelectedSharedItem[]>([]);
  const [uploadedItems, setUploadedItems] = useState<UploadResponse["uploads"]>([]);
  const [filterPreset, setFilterPreset] = useState("all");
  const [customIncludes, setCustomIncludes] = useState("");
  const [excludePatterns, setExcludePatterns] = useState("");
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [showHidden, setShowHidden] = useState(false);
  const [section, setSection] = useState<"add" | "process" | "activity">("add");
  const [libraryGoal, setLibraryGoal] = useState<"embed" | "synthesize" | "reextract" | "enrich" | "custom">("embed");
  const [runExtraction, setRunExtraction] = useState(true);
  const [extractMode, setExtractMode] = useState<"missing" | "reprocess">("missing");
  const [extractionPolicy, setExtractionPolicy] = useState<"make_primary" | "save_variant">("make_primary");
  const [synthesize, setSynthesize] = useState(true);
  const [embed, setEmbed] = useState(true);
  const [chunkingMethod, setChunkingMethod] = useState<ChunkingMethod>("sentence_window");
  const [chunkSize, setChunkSize] = useState(768);
  const [chunkOverlap, setChunkOverlap] = useState(128);
  const [enrich, setEnrich] = useState(false);
  const [selectedSynthesizer, setSelectedSynthesizer] = useState("");
  const [selectedEnricher, setSelectedEnricher] = useState("");
  const [extractorOverrides, setExtractorOverrides] = useState<Record<string, string>>({});
  const [expertContext, setExpertContext] = useState("");
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [rescanResult, setRescanResult] = useState<SourceRescanResponse | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [controllingRun, setControllingRun] = useState<string | null>(null);

  const selectedFilter = FILE_FILTERS.find(
    (option) => option.value === filterPreset,
  ) ?? FILE_FILTERS[0];
  const includePatterns = filterPreset === "custom"
    ? customIncludes
    : selectedFilter.patterns;
  const deferredIncludePatterns = useDeferredValue(includePatterns);
  const deferredExcludePatterns = useDeferredValue(excludePatterns);
  const chunkSettingsValid = chunkingMethod === "paragraph"
    || (chunkSize > 0 && chunkOverlap >= 0 && chunkOverlap < chunkSize);

  const rootBrowse = useQuery({
    queryKey: ["intake", "browse", "shared-root"],
    queryFn: () => browseIntake(),
  });
  const browse = useQuery({
    queryKey: [
      "intake",
      "browse",
      path,
      deferredIncludePatterns,
      deferredExcludePatterns,
      showHidden,
    ],
    queryFn: () => browseIntake(
      path || undefined,
      deferredIncludePatterns,
      deferredExcludePatterns,
      showHidden,
    ),
  });
  const runs = useQuery({
    queryKey: ["processing-runs"],
    queryFn: listProcessingRuns,
    refetchInterval: (query) => query.state.data?.runs.some(
      (run) => ["queued", "pending", "running", "pausing", "cancelling"].includes(run.status),
    ) ? 1500 : 5000,
  });
  const readiness = useQuery({
    queryKey: ["intake", "readiness"],
    queryFn: getIntakeReadiness,
    staleTime: 30_000,
  });
  const availableSynthesizers = readiness.data?.synthesizers.filter(
    (item) => item.available,
  ) ?? [];
  const configuredSynthesizer = readiness.data?.defaults.synthesizer;
  const effectiveSynthesizer = selectedSynthesizer
    || availableSynthesizers.find((item) => item.id === configuredSynthesizer)?.id
    || availableSynthesizers.find((item) => item.id === "local.extractive-preview")?.id
    || availableSynthesizers[0]?.id
    || "";

  const sharedRootPath = rootBrowse.data?.current_path ?? "";
  const queuePaths = useMemo(() => {
    const sharedPaths = includeSharedRoot
      ? (sharedRootPath ? [sharedRootPath] : [])
      : selectedSharedItems.map((item) => item.path);
    return [
      ...sharedPaths,
      ...uploadedItems.map((item) => item.path),
    ];
  }, [
    includeSharedRoot,
    selectedSharedItems,
    sharedRootPath,
    uploadedItems,
  ]);

  const preview = useQuery({
    queryKey: [
      "intake",
      "preview",
      queuePaths,
      includeSubfolders,
      deferredIncludePatterns,
      deferredExcludePatterns,
      showHidden,
      extractorOverrides,
      section,
      runExtraction,
      extractMode,
      synthesize,
      embed,
      chunkingMethod,
      chunkSize,
      chunkOverlap,
      enrich,
      effectiveSynthesizer,
      selectedEnricher,
    ],
    queryFn: () => resolveIntake({
      queue_paths: queuePaths,
      include_subfolders: includeSubfolders,
      include_patterns: deferredIncludePatterns,
      exclude_patterns: deferredExcludePatterns,
      show_hidden: showHidden,
      extractor_overrides: extractorOverrides,
      workflow: section === "process" ? "library" : "intake",
      run_extraction: runExtraction,
      extract_mode: extractMode,
      synthesizer_name: synthesize
        ? (effectiveSynthesizer || null)
        : null,
      build_embeddings: embed,
      chunking_method: chunkingMethod,
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
      enricher_name: enrich
        ? (selectedEnricher || readiness.data?.defaults.enricher || "local.stats-keywords")
        : null,
    }),
    enabled: queuePaths.length > 0 && section !== "activity",
  });

  const recentRuns = useMemo(
    () => runs.data?.runs.slice(0, 10) ?? [],
    [runs.data],
  );

  const controlRun = async (run: ProcessingRun, action: "pause" | "resume" | "cancel") => {
    setControllingRun(`${run.id}:${action}`);
    try {
      const result = await controlProcessingRun(run.id, action);
      setNotice({
        severity: "info",
        text: action === "pause"
          ? "Pause requested. OSII will finish the current file, then free the worker for another run."
          : action === "cancel"
            ? "Cancellation requested. OSII will finish the current file, then stop this run."
            : "Run resumed. Completed files will not be repeated.",
      });
      await queryClient.invalidateQueries({ queryKey: ["processing-runs"] });
      if (result.status === "paused" || result.status === "cancelled") {
        await runs.refetch();
      }
    } catch (error) {
      setNotice({
        severity: "error",
        text: error instanceof Error ? error.message : `Could not ${action} run.`,
      });
    } finally {
      setControllingRun(null);
    }
  };

  const addSharedEntry = (entry: QueueBrowseEntry) => {
    setIncludeSharedRoot(false);
    setSelectedSharedItems((items) => (
      items.some((item) => item.path === entry.path)
        ? items
        : [...items, entry]
    ));
  };

  const selectCurrentFolder = () => {
    if (!browse.data?.current_path) return;
    addSharedEntry({
      name: browse.data.display_path || "Shared root",
      display: browse.data.display_path || "Shared root",
      path: browse.data.current_path,
      processed: false,
      size_bytes: null,
      type: "folder",
    });
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    setUploading(true);
    setNotice(null);
    try {
      const result = await uploadQueueFiles(files);
      setUploadedItems((items) => [
        ...items,
        ...result.uploads.filter(
          (upload) => !items.some((item) => item.path === upload.path),
        ),
      ]);
      setIncludeSharedRoot(false);
      setSelectedSharedItems([]);
      setNotice({
        severity: "success",
        text: `${result.uploads.length} file(s) uploaded. This intake now targets the uploaded files only.`,
      });
    } catch (error) {
      setNotice({
        severity: "error",
        text: error instanceof Error ? error.message : "Upload failed.",
      });
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  const rescanSources = async (apply: boolean) => {
    setRescanning(true);
    setNotice(null);
    try {
      const result = await rescanSourcePaths(apply);
      setRescanResult(result);
      if (apply) {
        setNotice({
          severity: "success",
          text: `${result.applied?.moved_updated ?? 0} moved source path(s) remapped by matching file content hashes.`,
        });
        await queryClient.invalidateQueries();
      }
    } catch (error) {
      setNotice({
        severity: "error",
        text: error instanceof Error ? error.message : "Could not rescan source paths.",
      });
    } finally {
      setRescanning(false);
    }
  };

  const start = async () => {
    if (!queuePaths.length || !preview.data?.preview.matched_count) return;
    setStarting(true);
    setNotice(null);
    try {
      const run = await createProcessingRun({
        queue_paths: queuePaths,
        include_subfolders: includeSubfolders,
        include_patterns: includePatterns,
        exclude_patterns: excludePatterns,
        show_hidden: showHidden,
        extractor_overrides: extractorOverrides,
        workflow: section === "process" ? "library" : "intake",
        run_extraction: runExtraction,
        extract_mode: extractMode,
        extraction_policy: extractionPolicy,
        synthesizer_name: synthesize
          ? (effectiveSynthesizer || null)
          : null,
        build_embeddings: embed,
        chunking_method: chunkingMethod,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        enricher_name: enrich
          ? (selectedEnricher || readiness.data?.defaults.enricher || "local.stats-keywords")
          : null,
        expert_context: expertContext.trim() || null,
      });
      setNotice({
        severity: "success",
        text: `${section === "process" ? "Processing" : "Intake"} run ${run.id} is queued for ${run.resolved_count ?? preview.data.preview.matched_count} file(s).`,
      });
      setUploadedItems([]);
      setSelectedSharedItems([]);
      setIncludeSharedRoot(true);
      setExpertContext("");
      await queryClient.invalidateQueries({ queryKey: ["processing-runs"] });
      setSection("activity");
    } catch (error) {
      setNotice({
        severity: "error",
        text: error instanceof Error ? error.message : "Could not start intake.",
      });
    } finally {
      setStarting(false);
    }
  };

  const chooseLibraryGoal = (goal: typeof libraryGoal) => {
    setLibraryGoal(goal);
    if (goal === "embed") {
      setRunExtraction(false); setSynthesize(false); setEmbed(true); setEnrich(false);
    } else if (goal === "synthesize") {
      setRunExtraction(false); setSynthesize(true); setEmbed(false); setEnrich(false);
    } else if (goal === "reextract") {
      setRunExtraction(true); setExtractMode("reprocess"); setSynthesize(false); setEmbed(false); setEnrich(false);
    } else if (goal === "enrich") {
      setRunExtraction(false); setSynthesize(false); setEmbed(false); setEnrich(true);
    }
  };

  const changeSection = (next: "add" | "process" | "activity") => {
    setSection(next);
    if (next === "add") {
      setRunExtraction(true); setExtractMode("missing"); setExtractionPolicy("make_primary");
      setSynthesize(true); setEmbed(true); setEnrich(false);
    } else if (next === "process") {
      chooseLibraryGoal(libraryGoal);
    }
  };

  const matchedCount = preview.data?.preview.matched_count ?? 0;
  const queuedDocumentCount = section === "process"
    ? (preview.data?.preview.processing_plan?.unique_document_count ?? matchedCount)
    : matchedCount;
  const embeddingStatus = readiness.data?.embedders.find(
    (embedder) => embedder.id === readiness.data?.defaults.embedder,
  ) ?? readiness.data?.embedders[0];
  const embeddingAvailable = Boolean(embeddingStatus?.available);
  const extractorStatus = (name: string) => readiness.data?.extractors.find(
    (extractor) => (
      extractor.id === name
      || extractor.aliases?.includes(name)
    ),
  );
  const unavailableExtractorPlan = preview.data?.preview.extractor_plan.filter(
    (plan) => !extractorStatus(plan.extractor)?.available,
  ) ?? [];
  const extractorPlanReady = (
    Boolean(readiness.data)
    && unavailableExtractorPlan.length === 0
  );

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>Intake</Typography>
        <Typography color="text.secondary">
          Add documents, extend your current library, and monitor processing without mixing those tasks together.
        </Typography>
      </Stack>

      <Paper variant="outlined" sx={{ px: 1 }}>
        <Tabs
          value={section}
          onChange={(_, value) => changeSection(value)}
          variant="scrollable"
          allowScrollButtonsMobile
          aria-label="Intake sections"
        >
          <Tab value="add" label="Add files" />
          <Tab value="process" label="Process library" />
          <Tab value="activity" label="Activity" />
        </Tabs>
      </Paper>

      {notice ? <Alert severity={notice.severity}>{notice.text}</Alert> : null}

      {section !== "activity" ? <>

      {section === "process" ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Stack spacing={0.25}>
              <Typography fontWeight={700}>What would you like to add or improve?</Typography>
              <Typography variant="body2" color="text.secondary">
                OSII reuses the current primary extraction unless you explicitly upgrade it.
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {([
                ["embed", "Add embeddings"],
                ["synthesize", "Generate summaries"],
                ["reextract", "Upgrade extraction"],
                ["enrich", "Run enrichment"],
                ["custom", "Custom workflow"],
              ] as const).map(([value, label]) => (
                <Button
                  key={value}
                  variant={libraryGoal === value ? "contained" : "outlined"}
                  onClick={() => chooseLibraryGoal(value)}
                >
                  {label}
                </Button>
              ))}
            </Stack>
            {libraryGoal === "reextract" ? (
              <Alert severity="info">
                The new extraction is saved as an immutable version. Making it primary changes what future chunking, embeddings, summaries, and enrichments use; the previous version remains available.
              </Alert>
            ) : null}
          </Stack>
        </Paper>
      ) : null}

      <Alert
        severity="info"
        action={(
          <Button color="inherit" size="small" onClick={() => navigate("/admin/processors")}>
            Open Setup
          </Button>
        )}
      >
        <strong>Basic document reading is included.</strong> Open Setup only when you need OCR, Apache Tika, semantic embeddings, or generated summaries.
      </Alert>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            justifyContent="space-between"
            spacing={1}
          >
            <Stack spacing={0.25}>
              <Typography fontWeight={700}>Document scope</Typography>
              <Typography variant="body2" color="text.secondary">
                The default scope is every file under the configured source root. Choose individual paths only when a broad folder selection is not suitable.
              </Typography>
            </Stack>
            {preview.data ? (
              <Chip
                color="primary"
                variant="outlined"
                label={`${preview.data.preview.processed_count} already processed`}
              />
            ) : null}
          </Stack>

          <Paper variant="outlined" sx={{ p: 1.5, bgcolor: "action.hover" }}>
            <Stack spacing={1}>
              <Stack
                direction={{ xs: "column", md: "row" }}
                justifyContent="space-between"
                alignItems={{ md: "center" }}
                spacing={1}
              >
                <Stack spacing={0.25}>
                  <Typography variant="body2" fontWeight={700}>Originals moved or reorganized?</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Rescan the configured source root and match existing OSII objects by exact file-content hash. Previewing does not change files or rerun extraction.
                  </Typography>
                </Stack>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<RefreshOutlinedIcon />}
                  disabled={rescanning}
                  onClick={() => void rescanSources(false)}
                >
                  {rescanning ? "Scanning…" : "Rescan source paths"}
                </Button>
              </Stack>
              {rescanResult ? (
                <Alert
                  severity={rescanResult.applied ? "success" : "info"}
                  action={!rescanResult.applied && rescanResult.summary.moved > 0 ? (
                    <Button
                      color="inherit"
                      size="small"
                      disabled={rescanning}
                      onClick={() => void rescanSources(true)}
                    >
                      Apply {rescanResult.summary.moved} path update{rescanResult.summary.moved === 1 ? "" : "s"}
                    </Button>
                  ) : undefined}
                >
                  {rescanResult.summary.moved} moved · {rescanResult.summary.missing_source} missing · {rescanResult.summary.changed} changed in place · {rescanResult.summary.new_files} new. New and changed files are left for a normal Intake run.
                </Alert>
              ) : null}
            </Stack>
          </Paper>

          <FormControlLabel
            control={(
              <Checkbox
                checked={includeSharedRoot}
                onChange={(event) => setIncludeSharedRoot(event.target.checked)}
              />
            )}
            label="Include every file in the configured source root"
          />

          <Accordion variant="outlined" disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
              <Stack>
                <Typography fontWeight={600}>Choose specific paths</Typography>
                <Typography variant="caption" color="text.secondary">
                  Advanced: use this for a folder subset or an exceptional file.
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={1.5}>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                  <TextField
                    size="small"
                    fullWidth
                    label="Current folder (inside source root)"
                    value={path}
                    onChange={(event) => setPath(event.target.value)}
                    placeholder="Leave blank for source root"
                    helperText="Navigate here or click a folder below; this is not an operating-system file picker."
                  />
                  <Button variant="outlined" onClick={() => setPath("")}>
                    Root
                  </Button>
                  <Button
                    variant="contained"
                    startIcon={<FolderOutlinedIcon />}
                    onClick={selectCurrentFolder}
                    disabled={!browse.data?.current_path}
                  >
                    Select this folder
                  </Button>
                </Stack>

                <Alert severity="info" sx={{ py: 0.25 }}>
                  OSII browses only within <code>OSII_SOURCE_DIR</code>. A mounted shared or network drive works when that setting points to the drive and the OSII process has access; restart <code>make dev</code> after changing it.
                </Alert>

                {browse.isLoading ? <LinearProgress /> : null}
                <List
                  dense
                  sx={{
                    maxHeight: 300,
                    overflow: "auto",
                    border: 1,
                    borderColor: "divider",
                    borderRadius: 1,
                  }}
                >
                  {(browse.data?.entries ?? []).map((entry) => {
                    const isSelected = selectedSharedItems.some(
                      (item) => item.path === entry.path,
                    );
                    const secondary = entry.type === "folder"
                      ? "Folder"
                      : [
                        parentDisplay(entry.display),
                        formatSize(entry.size_bytes),
                      ].filter(Boolean).join(" · ");
                    return (
                      <ListItem
                        key={entry.path}
                        disablePadding
                        secondaryAction={(
                          <Stack direction="row" spacing={0.5} alignItems="center">
                            {entry.processed ? (
                              <Chip size="small" color="success" label="Processed" />
                            ) : null}
                            <Button
                              size="small"
                              startIcon={<AddOutlinedIcon />}
                              disabled={isSelected}
                              onClick={() => addSharedEntry(entry)}
                            >
                              {isSelected ? "Selected" : "Add"}
                            </Button>
                          </Stack>
                        )}
                      >
                        <ListItemButton
                          selected={isSelected}
                          onClick={() => (
                            entry.type === "folder"
                              ? setPath(entry.path)
                              : addSharedEntry(entry)
                          )}
                          sx={{ pr: 20 }}
                        >
                          <ListItemText
                            primary={entry.name}
                            secondary={secondary}
                            primaryTypographyProps={{ noWrap: true }}
                            secondaryTypographyProps={{ noWrap: true }}
                          />
                        </ListItemButton>
                      </ListItem>
                    );
                  })}
                </List>

                {selectedSharedItems.length ? (
                  <Stack spacing={0.75}>
                    <Typography variant="caption" color="text.secondary">
                      Specific shared selections
                    </Typography>
                    {selectedSharedItems.map((item) => (
                      <Stack
                        key={item.path}
                        direction="row"
                        alignItems="center"
                        justifyContent="space-between"
                        spacing={1}
                      >
                        <Stack minWidth={0}>
                          <Typography variant="body2" noWrap>{item.name}</Typography>
                          <Typography variant="caption" color="text.secondary" noWrap>
                            {item.type === "file"
                              ? parentDisplay(item.display)
                              : item.display}
                          </Typography>
                        </Stack>
                        <Button
                          size="small"
                          onClick={() => setSelectedSharedItems(
                            (items) => items.filter(
                              (candidate) => candidate.path !== item.path,
                            ),
                          )}
                        >
                          Remove
                        </Button>
                      </Stack>
                    ))}
                  </Stack>
                ) : null}
              </Stack>
            </AccordionDetails>
          </Accordion>
        </Stack>
      </Paper>

      {section === "add" ? <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>One-off uploads</Typography>
            <Typography variant="body2" color="text.secondary">
              Upload files that do not belong in the shared corpus. Uploading switches this intake to those files only.
            </Typography>
          </Stack>
          <Button
            component="label"
            variant="outlined"
            startIcon={<UploadFileOutlinedIcon />}
            disabled={uploading}
            sx={{ alignSelf: "flex-start" }}
          >
            {uploading ? "Uploading…" : "Choose files to upload"}
            <input hidden type="file" multiple onChange={handleUpload} />
          </Button>
          {uploadedItems.map((item) => (
            <Stack
              key={item.path}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              spacing={1}
            >
              <Stack minWidth={0}>
                <Typography variant="body2" noWrap>{item.name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  One-off upload · {formatSize(item.size_bytes)}
                </Typography>
              </Stack>
              <Button
                size="small"
                onClick={() => setUploadedItems(
                  (items) => items.filter(
                    (candidate) => candidate.path !== item.path,
                  ),
                )}
              >
                Remove
              </Button>
            </Stack>
          ))}
        </Stack>
      </Paper> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>Scope rules</Typography>
            <Typography variant="body2" color="text.secondary">
              Rules narrow the source scope above; they never replace it. The default is all files under the configured source root with no include rule.
            </Typography>
          </Stack>

          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField
              select
              fullWidth
              size="small"
              label="File types"
              value={filterPreset}
              onChange={(event) => setFilterPreset(event.target.value)}
            >
              {FILE_FILTERS.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              fullWidth
              size="small"
              multiline
              minRows={2}
              label="Exclude patterns"
              placeholder={"*.tmp\narchive/**"}
              value={excludePatterns}
              onChange={(event) => setExcludePatterns(event.target.value)}
            />
          </Stack>

          {filterPreset === "custom" ? (
            <TextField
              fullWidth
              size="small"
              multiline
              minRows={3}
              label="Include patterns"
              placeholder={"*.pdf\nreports/**/*.csv"}
              value={customIncludes}
              onChange={(event) => setCustomIncludes(event.target.value)}
            />
          ) : null}

          <Stack>
            <FormControlLabel
              control={(
                <Checkbox
                  checked={includeSubfolders}
                  onChange={(event) => setIncludeSubfolders(event.target.checked)}
                />
              )}
              label="Include subfolders"
            />
            <FormControlLabel
              control={(
                <Checkbox
                  checked={showHidden}
                  onChange={(event) => setShowHidden(event.target.checked)}
                />
              )}
              label="Include hidden files"
            />
          </Stack>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack
            direction={{ xs: "column", md: "row" }}
            justifyContent="space-between"
            spacing={1}
          >
            <Stack spacing={0.25}>
              <Typography fontWeight={700}>Extraction for this run</Typography>
              <Typography variant="body2" color="text.secondary">
                These choices are calculated from the document scope and file rules above. Completed files remain browsable while processing continues.
              </Typography>
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <Button
                size="small"
                variant="outlined"
                startIcon={<RefreshOutlinedIcon />}
                onClick={() => void queryClient.invalidateQueries({
                  queryKey: ["intake", "readiness"],
                })}
              >
                Retest tools
              </Button>
              <Button
                size="small"
                variant="outlined"
                startIcon={<SettingsOutlinedIcon />}
                onClick={() => navigate("/admin/processors")}
              >
                Open Setup
              </Button>
            </Stack>
          </Stack>

          {readiness.isLoading ? <LinearProgress /> : null}
          {readiness.isError ? (
            <Alert severity="error">
              Tool readiness could not be tested. Intake is paused until the tools can be checked.
            </Alert>
          ) : null}

          {readiness.data ? (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {runExtraction ? (
                <Chip
                  color={extractorPlanReady ? "success" : "error"}
                  variant="outlined"
                  label={extractorPlanReady
                    ? "Selected text extractors are running"
                    : "A selected extractor needs setup"}
                />
              ) : (
                <Chip color="success" variant="outlined" label="Using current extraction" />
              )}
              <Chip
                color={embeddingAvailable ? "success" : "default"}
                variant="outlined"
                label={embeddingAvailable
                  ? `${embeddingStatus?.display_name ?? "Embedding method"} is usable`
                  : "No embedding model — BM25 keyword search still works"}
              />
              <Chip
                color="success"
                variant="outlined"
                label={`${readiness.data.enrichers.filter((item) => item.available).length} enrichment methods available`}
              />
            </Stack>
          ) : null}

          {runExtraction ? (
            <Stack spacing={1}>
              <Typography variant="subtitle2">Extractor rules for matched files</Typography>
              {(preview.data?.preview.extractor_plan ?? []).map((plan) => {
                const selectedStatus = extractorStatus(plan.extractor);
                return (
                  <Paper key={plan.extension} variant="outlined" sx={{ p: 1.5 }}>
                    <Stack
                      direction={{ xs: "column", md: "row" }}
                      alignItems={{ md: "center" }}
                      justifyContent="space-between"
                      spacing={1.5}
                    >
                      <Stack minWidth={0}>
                        <Typography fontWeight={600}>
                          {plan.extension} · {plan.count} file{plan.count === 1 ? "" : "s"}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" noWrap>
                          {plan.sample.join(", ")}
                        </Typography>
                      </Stack>
                      <TextField
                        select
                        size="small"
                        label="Extractor"
                        value={selectedStatus?.id ?? plan.extractor}
                        onChange={(event) => setExtractorOverrides((current) => ({
                          ...current,
                          [plan.extension]: event.target.value,
                        }))}
                        sx={{ minWidth: 240 }}
                      >
                        {(readiness.data?.extractors ?? []).map((extractor) => (
                          <MenuItem
                            key={extractor.id}
                            value={extractor.id}
                            disabled={!extractor.available}
                          >
                            {extractor.display_name}
                            {extractor.available ? "" : " — unavailable"}
                          </MenuItem>
                        ))}
                      </TextField>
                      <Chip
                        size="small"
                        color={selectedStatus?.available ? "success" : "error"}
                        label={selectedStatus?.available ? "Ready" : "Unavailable"}
                        sx={{ alignSelf: { xs: "flex-start", md: "center" } }}
                      />
                    </Stack>
                  </Paper>
                );
              })}
              {preview.isLoading ? <LinearProgress /> : null}
              {!preview.isLoading && !(preview.data?.preview.extractor_plan.length) ? (
                <Typography variant="body2" color="text.secondary">
                  No files currently match the source scope and rules above.
                </Typography>
              ) : null}
            </Stack>
          ) : (
            <Alert severity="success">
              Extraction will not run. OSII will reuse each document&apos;s current primary extraction.
            </Alert>
          )}

          {runExtraction && unavailableExtractorPlan.length ? (
            <Alert severity="error">
              Start the required extractor service or choose another ready extractor.
            </Alert>
          ) : null}
          {readiness.data?.external.length ? (
            <Typography variant="caption" color="text.secondary">
              {readiness.data.external.filter((item) => item.available).length} of{" "}
              {readiness.data.external.length} registered external tools responded.
              Open Setup to run their full contract tests.
            </Typography>
          ) : null}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>Expert context</Typography>
            <Typography variant="body2" color="text.secondary">
              Add facts a subject-matter expert knows about the selected documents or folders. OSII saves this context with the intake and supplies it to processors that can use it.
            </Typography>
          </Stack>
          <TextField
            fullWidth
            multiline
            minRows={4}
            label="Expert context (optional)"
            placeholder="Example: These folders contain repeated calibration runs. Temperatures are ambient unless explicitly marked, and filenames beginning with REF are control measurements."
            value={expertContext}
            onChange={(event) => setExpertContext(event.target.value)}
            inputProps={{ maxLength: 20_000 }}
            helperText={`${expertContext.length.toLocaleString()} / 20,000 characters · Applies to every matched document in this run.`}
          />
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>{section === "process" ? "Processing steps" : "Derived outputs"}</Typography>
            <Typography variant="body2" color="text.secondary">
              {section === "process"
                ? "Only the selected steps run. Downstream work uses each document's current primary extraction."
                : "New documents receive a primary extraction. These optional steps create additional representations."}
            </Typography>
          </Stack>
          {section === "process" && (libraryGoal === "reextract" || libraryGoal === "custom") ? (
            <Stack spacing={1}>
              <FormControlLabel
                control={<Checkbox checked={runExtraction} onChange={(event) => setRunExtraction(event.target.checked)} />}
                label="Run extraction"
              />
              {runExtraction ? (
                <TextField
                  select
                  size="small"
                  label="After the new extraction finishes"
                  value={extractionPolicy}
                  onChange={(event) => setExtractionPolicy(event.target.value as typeof extractionPolicy)}
                >
                  <MenuItem value="make_primary">Make it primary and preserve the previous version</MenuItem>
                  <MenuItem value="save_variant">Save as another version; keep the current primary</MenuItem>
                </TextField>
              ) : null}
            </Stack>
          ) : null}
          <FormControlLabel
            control={(
              <Checkbox
                checked={synthesize}
                disabled={extractionPolicy === "save_variant" && runExtraction}
                onChange={(event) => setSynthesize(event.target.checked)}
              />
            )}
            label="Generate document summaries"
          />
          {synthesize ? (
            <TextField
              select
              size="small"
              label="Synthesizer"
              value={effectiveSynthesizer}
              onChange={(event) => setSelectedSynthesizer(event.target.value)}
            >
              {availableSynthesizers.map((item) => (
                <MenuItem key={item.id} value={item.id}>{item.display_name}</MenuItem>
              ))}
            </TextField>
          ) : null}
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
            {effectiveSynthesizer === "local.extractive-preview"
              ? "Using the no-AI baseline: OSII copies cited source excerpts and does not generate new prose."
              : "Using a connected model-backed synthesizer; its provider and model are recorded with the result."}
          </Typography>
          {embed ? (
            <Accordion variant="outlined" disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
                <Stack spacing={0.2}>
                  <Typography variant="body2" fontWeight={600}>Retrieval chunking</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {chunkingMethod === "sentence_window"
                      ? `${chunkSize} characters with about ${chunkOverlap} characters of sentence-aligned overlap`
                      : chunkingMethod === "window"
                        ? `${chunkSize} characters with ${chunkOverlap} characters of fixed overlap`
                        : "One chunk per paragraph; no overlap"}
                  </Typography>
                </Stack>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={1.5}>
                  <TextField
                    select
                    size="small"
                    label="Chunking strategy"
                    value={chunkingMethod}
                    onChange={(event) => setChunkingMethod(event.target.value as ChunkingMethod)}
                  >
                    <MenuItem value="sentence_window">Sentence-aligned windows (recommended)</MenuItem>
                    <MenuItem value="paragraph">Paragraphs (compatibility)</MenuItem>
                    <MenuItem value="window">Fixed character windows</MenuItem>
                  </TextField>
                  {chunkingMethod !== "paragraph" ? (
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                      <TextField
                        size="small"
                        type="number"
                        label="Maximum characters"
                        value={chunkSize}
                        inputProps={{ min: 100, step: 100 }}
                        onChange={(event) => setChunkSize(Number(event.target.value))}
                      />
                      <TextField
                        size="small"
                        type="number"
                        label="Overlap characters"
                        value={chunkOverlap}
                        inputProps={{ min: 0, step: 25 }}
                        error={!chunkSettingsValid}
                        helperText={!chunkSettingsValid ? "Overlap must be smaller than the chunk size." : "Preserves context across boundaries."}
                        onChange={(event) => setChunkOverlap(Number(event.target.value))}
                      />
                    </Stack>
                  ) : null}
                  <Typography variant="caption" color="text.secondary">
                    Sentence-aligned windows preserve exact character offsets and source-page grounding. Changing these settings rebuilds both semantic and BM25 indexes.
                  </Typography>
                </Stack>
              </AccordionDetails>
            </Accordion>
          ) : null}
          {embeddingStatus?.index_rebuild_required ? (
            <Alert severity="warning">
              {embeddingStatus.indexed_model
                ? `The existing index uses ${embeddingStatus.indexed_model}; this run will rebuild it for ${embeddingStatus.model}.`
                : `The current semantic index is incompatible and will be rebuilt for ${embeddingStatus.model}.`}
            </Alert>
          ) : null}
          <FormControlLabel
            control={(
              <Checkbox
                checked={embed}
                disabled={(!embeddingAvailable && !embed) || (extractionPolicy === "save_variant" && runExtraction)}
                onChange={(event) => setEmbed(event.target.checked)}
              />
            )}
            label="Build semantic embeddings"
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
            {embeddingAvailable
              ? `Ready${embeddingStatus?.model ? `: ${embeddingStatus.model}` : ""}.${embeddingStatus?.lexical ? " Hashing vectors provide approximate lexical similarity, not semantic understanding." : ""}`
              : "Unavailable and cannot be queued. Lexical search remains available without an embedder."}
          </Typography>
          {section === "process" && (libraryGoal === "enrich" || libraryGoal === "custom") ? (
            <>
              <FormControlLabel
                control={(
                  <Checkbox
                    checked={enrich}
                    disabled={extractionPolicy === "save_variant" && runExtraction}
                    onChange={(event) => setEnrich(event.target.checked)}
                  />
                )}
                label="Run enrichment"
              />
              {enrich ? (
                <TextField
                  select
                  size="small"
                  label="Enricher"
                  value={selectedEnricher || readiness.data?.defaults.enricher || ""}
                  onChange={(event) => setSelectedEnricher(event.target.value)}
                >
                  {(readiness.data?.enrichers ?? []).filter((item) => item.available).map((item) => (
                    <MenuItem key={item.id} value={item.id}>{item.display_name}</MenuItem>
                  ))}
                </TextField>
              ) : null}
            </>
          ) : null}
          {extractionPolicy === "save_variant" && runExtraction ? (
            <Alert severity="info">
              Downstream steps are disabled because this new extraction will not become primary.
            </Alert>
          ) : null}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>Review and start</Typography>
            <Typography variant="body2" color="text.secondary">
              Review exactly what will run before adding it to the sequential processing queue.
            </Typography>
          </Stack>

          {preview.isLoading || rootBrowse.isLoading ? <LinearProgress /> : null}
          {preview.isError ? (
            <Alert severity="error">
              Could not preview this intake.
              {preview.error instanceof Error ? ` ${preview.error.message}` : ""}
            </Alert>
          ) : null}

          {preview.data ? (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip color="primary" label={`${matchedCount} files match`} />
              <Chip
                color="success"
                variant="outlined"
                label={`${preview.data.preview.processed_count} already processed`}
              />
              <Chip
                variant="outlined"
                label={`${preview.data.preview.unprocessed_count} new`}
              />
              <Chip
                variant="outlined"
                label={preview.data.preview.total_size_human}
              />
            </Stack>
          ) : null}

          {expertContext.trim() ? (
            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: "action.hover" }}>
              <Stack spacing={0.5}>
                <Typography variant="caption" fontWeight={700} color="text.secondary">
                  EXPERT CONTEXT INCLUDED
                </Typography>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                  {expertContext.trim()}
                </Typography>
              </Stack>
            </Paper>
          ) : (
            <Typography variant="caption" color="text.secondary">
              No expert context supplied. You can still start this run.
            </Typography>
          )}

          {preview.data?.preview.processing_plan ? (
            <Stack spacing={0.75}>
              {preview.data.preview.processing_plan.steps.map((step) => (
                <Stack key={step.id} direction="row" justifyContent="space-between" spacing={2}>
                  <Typography variant="body2">{step.label}</Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {step.eligible_count} queued{step.current_count ? ` · ${step.current_count} already current` : ""}
                  </Typography>
                </Stack>
              ))}
              {preview.data.preview.processing_plan.blocked_count ? (
                <Alert severity="warning">
                  {preview.data.preview.processing_plan.blocked_count} document(s) have no extraction and will be skipped unless extraction is selected.
                </Alert>
              ) : null}
            </Stack>
          ) : null}

          {!includeSharedRoot && !selectedSharedItems.length && !uploadedItems.length ? (
            <Alert severity="info">
              Select a shared folder/file or upload one-off files.
            </Alert>
          ) : null}
          {preview.data && matchedCount === 0 ? (
            <Alert severity="warning">
              No files match the current source scope and intake rules.
            </Alert>
          ) : null}

          <Button
            variant="contained"
            startIcon={<PlayArrowOutlinedIcon />}
            disabled={
              !queuePaths.length
              || !matchedCount
              || starting
              || preview.isLoading
              || readiness.isLoading
              || (runExtraction && !extractorPlanReady)
              || (synthesize && !effectiveSynthesizer)
              || (embed && !embeddingAvailable)
              || (embed && !chunkSettingsValid)
              || (extractionPolicy === "save_variant" && runExtraction && (synthesize || embed || enrich))
            }
            onClick={() => void start()}
            sx={{ alignSelf: "flex-start" }}
          >
            {starting
              ? "Queueing work…"
              : `${section === "process" ? "Queue processing" : "Start intake"}${queuedDocumentCount ? ` (${queuedDocumentCount} document${queuedDocumentCount === 1 ? "" : "s"})` : ""}`}
          </Button>
        </Stack>
      </Paper>

      </> : null}

      {section === "activity" ? <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography fontWeight={700}>Processing activity</Typography>
          {recentRuns.some((run) => ["queued", "pending", "running", "pausing", "cancelling"].includes(run.status)) ? (
            <Alert severity="info">
              Runs use one worker and process files sequentially. Pause a long run to let a newly queued priority run go next; pausing or cancelling takes effect safely after the current file finishes.
            </Alert>
          ) : null}
          {recentRuns.map((run) => {
            const durations = completedFileDurations(run);
            const processorSeconds = durations.reduce((total, duration) => total + duration, 0);
            const averageSeconds = durations.length ? processorSeconds / durations.length : null;
            const remainingFiles = Math.max(0, (run.total ?? 0) - (run.completed ?? 0));
            const estimatedRemaining = averageSeconds == null ? null : averageSeconds * remainingFiles;
            const elapsedSeconds = secondsBetween(run.started_at, run.finished_at);
            const controllable = Boolean(run.workflow);
            const canPause = controllable && ["queued", "pending", "running"].includes(run.status);
            const canResume = controllable && run.status === "paused";
            const canCancel = controllable && ["queued", "pending", "running", "pausing", "paused"].includes(run.status);
            return (
              <Paper key={run.id} variant="outlined" sx={{ p: 1.5 }}>
              <Stack
                direction={{ xs: "column", sm: "row" }}
                justifyContent="space-between"
                spacing={1}
              >
                <Stack>
                  <Typography fontWeight={600}>
                    {run.workflow === "library" ? "Library processing" : "New file intake"} · {run.id.slice(0, 8)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {run.completed ?? 0} / {run.total ?? 0} files · {run.created_at}
                  </Typography>
                  {run.expert_context ? (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{
                        mt: 0.5,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      Expert context: {run.expert_context}
                    </Typography>
                  ) : null}
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                    {run.operations?.extract ? <Chip size="small" label="Extraction" /> : null}
                    {run.operations?.synthesize ? <Chip size="small" label="Synthesis" /> : null}
                    {run.operations?.embed ? <Chip size="small" label={`Embedding${run.indexing_status ? `: ${run.indexing_status}` : ""}`} /> : null}
                    {run.operations?.enrich ? <Chip size="small" label="Enrichment" /> : null}
                  </Stack>
                </Stack>
                <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                  {canPause ? (
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<PauseCircleOutlineOutlinedIcon />}
                      disabled={controllingRun !== null}
                      onClick={() => void controlRun(run, "pause")}
                    >
                      Pause
                    </Button>
                  ) : null}
                  {canResume ? (
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<PlayArrowOutlinedIcon />}
                      disabled={controllingRun !== null}
                      onClick={() => void controlRun(run, "resume")}
                    >
                      Resume
                    </Button>
                  ) : null}
                  {canCancel ? (
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      startIcon={<CancelOutlinedIcon />}
                      disabled={controllingRun !== null}
                      onClick={() => void controlRun(run, "cancel")}
                    >
                      Cancel
                    </Button>
                  ) : null}
                  <Chip
                    color={
                      run.status === "done"
                        ? "success"
                        : ["error", "cancelled"].includes(run.status)
                          ? "error"
                          : run.status === "paused"
                            ? "warning"
                            : "primary"
                    }
                    label={run.status}
                  />
                </Stack>
              </Stack>
              {run.started_at ? (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  Elapsed {formatDuration(elapsedSeconds)}
                  {durations.length ? ` · measured processor time ${formatDuration(processorSeconds)} · average ${formatDuration(averageSeconds)} per completed file` : ""}
                  {estimatedRemaining != null && remainingFiles > 0 ? ` · estimated remaining ${formatDuration(estimatedRemaining)}` : ""}
                </Typography>
              ) : null}
              {run.status === "pausing" ? <Alert severity="info" sx={{ mt: 1 }}>Finishing the current file before pausing.</Alert> : null}
              {run.status === "cancelling" ? <Alert severity="info" sx={{ mt: 1 }}>Finishing the current file before cancelling.</Alert> : null}
              {run.error ? <Alert severity="error" sx={{ mt: 1 }}>{run.error}</Alert> : null}
              {run.indexing_error ? <Alert severity="warning" sx={{ mt: 1 }}>{run.indexing_error}</Alert> : null}
              {(run.logs ?? []).slice(-2).map((line) => (
                <Typography
                  key={line}
                  variant="caption"
                  display="block"
                  color="text.secondary"
                >
                  {line}
                </Typography>
              ))}
              {(run.items ?? []).some((item) => item.started_at || item.duration_seconds != null) ? (
                <Accordion variant="outlined" disableGutters sx={{ mt: 1 }}>
                  <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
                    <Typography variant="body2" fontWeight={600}>File processing times</Typography>
                  </AccordionSummary>
                  <AccordionDetails sx={{ maxHeight: 300, overflow: "auto" }}>
                    <Stack spacing={1}>
                      {durations.length ? (
                        <Typography variant="caption" color="text.secondary">
                          Fastest {formatDuration(Math.min(...durations))} · slowest {formatDuration(Math.max(...durations))} · average {formatDuration(averageSeconds)}
                        </Typography>
                      ) : null}
                      {(run.items ?? []).map((item, index) => (
                        <Stack
                          key={`${item.display}-${index}`}
                          direction={{ xs: "column", sm: "row" }}
                          justifyContent="space-between"
                          spacing={0.5}
                        >
                          <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{item.display}</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                            {item.status} · {formatDuration(
                              item.duration_seconds ?? secondsBetween(item.started_at, item.finished_at),
                            )}
                          </Typography>
                        </Stack>
                      ))}
                    </Stack>
                  </AccordionDetails>
                </Accordion>
              ) : null}
              </Paper>
            );
          })}
          {!recentRuns.length ? (
            <Typography color="text.secondary">No intake runs yet.</Typography>
          ) : null}
        </Stack>
      </Paper> : null}
    </Stack>
  );
}
