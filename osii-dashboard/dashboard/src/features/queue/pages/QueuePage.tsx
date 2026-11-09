import { ProcessorStepControl } from "../components/ProcessorStepControl";
import {
  ChangeEvent,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiJson } from "../../../api/client";
import { FileSelectionList } from "../components/FileSelectionList";
import { IntakeSections } from "../components/IntakeSections";
import { ProcessingActivity } from "../components/ProcessingActivity";
import { WorkflowProgress } from "../../../components/discovery/WorkflowProgress";
import type { WorkflowStepId } from "../../../domain/workflow";

import {
  browseIntake,
  controlProcessingRun,
  createProcessingRun,
  getProcessingRunLogs,
  getIntakeReadiness,
  listProcessingRuns,
  recoverProcessingQueue,
  rescanSourcePaths,
  resolveIntake,
  uploadQueueFiles,
} from "../../../api/queue";
import type {
  QueueBrowseResponse,
  ProcessingRun,
  SourceRescanResponse,
  UploadResponse,
} from "../../../api/types";

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

export function QueuePage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedStep = searchParams.get("step");
  const [path, setPath] = useState("");
  const [selectedFolder, setSelectedFolder] =
    useState<QueueBrowseResponse | null>(null);
  const [selectingFolder, setSelectingFolder] = useState(false);
  const [folderError, setFolderError] = useState<string | null>(null);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [browsePath, setBrowsePath] = useState("");
  const [browseAddress, setBrowseAddress] = useState("");
  const [excludedPaths, setExcludedPaths] = useState<string[]>([]);
  const [visibleFileCount, setVisibleFileCount] = useState(50);
  const [uploadedItems, setUploadedItems] = useState<UploadResponse["uploads"]>(
    [],
  );
  const [filterPreset, setFilterPreset] = useState("all");
  const [customIncludes, setCustomIncludes] = useState("");
  const [excludePatterns, setExcludePatterns] = useState("");
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [showHidden, setShowHidden] = useState(false);
  const [section, setSection] = useState<"add" | "process" | "activity">(requestedStep === "index" ? "process" : "add");
  const [libraryGoal, setLibraryGoal] = useState<
    "embed" | "synthesize" | "reextract" | "enrich" | "custom"
  >("embed");
  const [runExtraction, setRunExtraction] = useState(requestedStep !== "index");
  const [extractMode, setExtractMode] = useState<"missing" | "reprocess">(
    "missing",
  );
  const [extractionPolicy, setExtractionPolicy] = useState<
    "make_primary" | "save_variant"
  >("make_primary");
  const [synthesize, setSynthesize] = useState(requestedStep !== "index");
  const [embed, setEmbed] = useState(true);
  const [chunkingMethod, setChunkingMethod] =
    useState<ChunkingMethod>("sentence_window");
  const [chunkSize, setChunkSize] = useState(768);
  const [chunkOverlap, setChunkOverlap] = useState(128);
  const [enrich, setEnrich] = useState(false);
  const [createCollection, setCreateCollection] = useState(false);
  const [collectionName, setCollectionName] = useState("");
  const [collectionDescription, setCollectionDescription] = useState("");
  const [selectedSynthesizer, setSelectedSynthesizer] = useState("");
  const [selectedEnricher, setSelectedEnricher] = useState("");
  const [expertContext, setExpertContext] = useState("");
  const [intakePreset, setIntakePreset] = useState("summary-search");
  const defaultsApplied = useRef(false);
  const intakeDefaults = useQuery({
    queryKey: ["intake", "defaults"],
    queryFn: () => apiJson<{
      preset: string; synthesize: boolean; build_embeddings: boolean; enrich: boolean;
      presets: { id: string; label: string; synthesize: boolean; build_embeddings: boolean; enrich: boolean }[];
      include_subfolders: boolean; show_hidden: boolean; include_patterns: string; exclude_patterns: string;
      chunk_size: number; chunk_overlap: number; synthesizer: string; enricher: string;
    }>("/api/intake/defaults"),
    staleTime: Infinity,
  });
  const applyIntakePreset = (id: string) => {
    const preset = intakeDefaults.data?.presets.find(item => item.id === id);
    if (!preset) return;
    setIntakePreset(id);
    setRunExtraction(true); setExtractMode("missing"); setExtractionPolicy("make_primary");
    setSynthesize(preset.synthesize); setEmbed(preset.build_embeddings); setEnrich(preset.enrich);
  };
  useEffect(() => {
    const defaults = intakeDefaults.data;
    if (!defaults || defaultsApplied.current) return;
    defaultsApplied.current = true;
    if (requestedStep !== "index") applyIntakePreset(defaults.preset);
    setIncludeSubfolders(defaults.include_subfolders); setShowHidden(defaults.show_hidden);
    if (defaults.include_patterns) { setFilterPreset("custom"); setCustomIncludes(defaults.include_patterns); }
    setExcludePatterns(defaults.exclude_patterns);
    setChunkSize(defaults.chunk_size); setChunkOverlap(defaults.chunk_overlap);
    setSelectedSynthesizer(defaults.synthesizer); setSelectedEnricher(defaults.enricher);
  }, [intakeDefaults.data]);
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [rescanResult, setRescanResult] = useState<SourceRescanResponse | null>(
    null,
  );
  const [notice, setNotice] = useState<Notice | null>(null);
  const [controllingRun, setControllingRun] = useState<string | null>(null);
  const [recoveringQueue, setRecoveringQueue] = useState(false);
  const [selectedLogRunId, setSelectedLogRunId] = useState<string | null>(null);

  const selectedFilter =
    FILE_FILTERS.find((option) => option.value === filterPreset) ??
    FILE_FILTERS[0];
  const includePatterns =
    filterPreset === "custom" ? customIncludes : selectedFilter.patterns;
  const deferredIncludePatterns = useDeferredValue(includePatterns);
  const deferredExcludePatterns = useDeferredValue(excludePatterns);
  const filtersUpdating =
    includePatterns !== deferredIncludePatterns ||
    excludePatterns !== deferredExcludePatterns;
  const chunkSettingsValid =
    chunkingMethod === "paragraph" ||
    (chunkSize > 0 && chunkOverlap >= 0 && chunkOverlap < chunkSize);

  const rootBrowse = useQuery({
    queryKey: ["intake", "browse", "shared-root"],
    queryFn: () => browseIntake(),
  });
  const browse = useQuery({
    queryKey: ["intake", "folders", browsePath],
    queryFn: () => browseIntake(browsePath || undefined),
    enabled: browseOpen,
  });
  useEffect(() => {
    if (rootBrowse.data && !selectedFolder) {
      setSelectedFolder(rootBrowse.data);
      setPath((draft) => draft.trim() ? draft : (rootBrowse.data.host_path ?? rootBrowse.data.current_path));
    }
  }, [rootBrowse.data, selectedFolder]);
  useEffect(() => {
    if (browse.data)
      setBrowseAddress(browse.data.host_path ?? browse.data.current_path);
  }, [browse.data]);
  const runs = useQuery({
    queryKey: ["processing-runs"],
    queryFn: listProcessingRuns,
    refetchInterval: (query) =>
      query.state.data?.runs.some((run) =>
        ["queued", "pending", "running", "pausing", "cancelling"].includes(
          run.status,
        ),
      )
        ? 1500
        : 5000,
  });
  const readiness = useQuery({
    queryKey: ["intake", "readiness"],
    queryFn: getIntakeReadiness,
    staleTime: 30_000,
    refetchInterval: 15_000,
  });
  const sourceStatus = readiness.data?.source;
  const availableSynthesizers =
    readiness.data?.synthesizers.filter((item) => item.available) ?? [];
  const configuredSynthesizer = readiness.data?.defaults.synthesizer;
  const effectiveSynthesizer =
    selectedSynthesizer ||
    availableSynthesizers.find((item) => item.id === configuredSynthesizer)
      ?.id ||
    availableSynthesizers.find((item) => item.id === "local.extractive-preview")
      ?.id ||
    availableSynthesizers[0]?.id ||
    "";

  const queuePaths = useMemo(() => {
    return [
      ...(selectedFolder ? [selectedFolder.current_path] : []),
      ...uploadedItems.map((item) => item.path),
    ];
  }, [selectedFolder, uploadedItems]);
  const folderChanged =
    path.trim() !==
    (selectedFolder?.host_path ?? selectedFolder?.current_path ?? "");

  const preview = useQuery({
    queryKey: [
      "intake",
      "preview",
      queuePaths,
      excludedPaths,
      includeSubfolders,
      deferredIncludePatterns,
      deferredExcludePatterns,
      showHidden,
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
    queryFn: () =>
      resolveIntake({
        queue_paths: queuePaths,
        excluded_paths: excludedPaths,
        include_subfolders: includeSubfolders,
        include_patterns: deferredIncludePatterns,
        exclude_patterns: deferredExcludePatterns,
        show_hidden: showHidden,
        workflow: section === "process" ? "library" : "intake",
        run_extraction: runExtraction,
        extract_mode: extractMode,
        synthesizer_name: synthesize ? effectiveSynthesizer || null : null,
        build_embeddings: embed,
        chunking_method: chunkingMethod,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        enricher_name: enrich
          ? selectedEnricher ||
            readiness.data?.defaults.enricher ||
            "local.stats-keywords"
          : null,
      }),
    enabled: queuePaths.length > 0 && section !== "activity",
  });

  const recentRuns = useMemo(
    () => runs.data?.runs.slice(0, 10) ?? [],
    [runs.data],
  );
  const selectedLogRun = recentRuns.find((run) => run.id === selectedLogRunId);
  const runLogs = useQuery({
    queryKey: ["processing-runs", selectedLogRunId, "logs"],
    queryFn: () => getProcessingRunLogs(selectedLogRunId ?? ""),
    enabled: section === "activity" && Boolean(selectedLogRunId),
    refetchInterval: selectedLogRun
      && ["queued", "pending", "running", "pausing", "cancelling"].includes(selectedLogRun.status)
      ? 1000
      : 5000,
  });
  const displayedLogLines = runLogs.data?.logs ?? selectedLogRun?.logs ?? [];

  useEffect(() => {
    if (section !== "activity" || selectedLogRunId || !recentRuns.length) return;
    const visibleRun = recentRuns.find((run) => (
      ["queued", "pending", "running", "pausing", "cancelling", "error"].includes(run.status)
    )) ?? recentRuns[0];
    setSelectedLogRunId(visibleRun.id);
  }, [recentRuns, section, selectedLogRunId]);



  const controlRun = async (run: ProcessingRun, action: "pause" | "resume" | "cancel" | "retry") => {
    setControllingRun(`${run.id}:${action}`);
    try {
      const result = await controlProcessingRun(run.id, action);
      setNotice({
        severity: "info",
        text: action === "pause"
          ? "Pause requested. OSII will finish the current file, then free the worker for another run."
          : action === "cancel"
            ? "Cancellation requested. OSII will finish the current file, then stop this run."
            : action === "retry"
              ? "The failed run is queued again. Files that already completed will not be repeated."
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

  const recoverQueue = async () => {
    setRecoveringQueue(true);
    try {
      const result = await recoverProcessingQueue();
      setNotice({
        severity: "info",
        text: result.recovered_count
          ? `${result.recovered_count} interrupted run(s) returned to a safe queue state.`
          : "No stale run was found. If the worker just stopped, wait 15 seconds and try again.",
      });
      await queryClient.invalidateQueries({ queryKey: ["processing-runs"] });
    } catch (error) {
      setNotice({
        severity: "error",
        text: error instanceof Error ? error.message : "Could not recover the processing queue.",
      });
    } finally {
      setRecoveringQueue(false);
    }
  };

  const selectFolder = async (requestedPath: string) => {
    setSelectingFolder(true);
    setFolderError(null);
    try {
      const folder = await browseIntake(requestedPath || undefined);
      setSelectedFolder(folder);
      setNotice(null);
      setPath(folder.host_path ?? folder.current_path);
      setExcludedPaths([]);
      setVisibleFileCount(50);
      if (!collectionName.trim())
        setCollectionName(folder.folder_name ?? folder.display_path);
      setBrowseOpen(false);
    } catch (error) {
      setFolderError(
        error instanceof Error ? error.message : "Could not open this folder.",
      );
    } finally {
      setSelectingFolder(false);
    }
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
      setNotice({
        severity: "success",
        text: `${result.uploads.length} uploaded file(s) added to this run. Your folder selection is still included.`,
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
    if (
      !queuePaths.length ||
      !preview.data?.preview.matched_count ||
      preview.isFetching ||
      preview.isError ||
      filtersUpdating ||
      selectingFolder ||
      folderChanged ||
      folderError ||
      (createCollection && !collectionName.trim())
    )
      return;
    setStarting(true);
    setNotice(null);
    try {
      const run = await createProcessingRun({
        queue_paths: queuePaths,
        excluded_paths: excludedPaths,
        include_subfolders: includeSubfolders,
        include_patterns: includePatterns,
        exclude_patterns: excludePatterns,
        show_hidden: showHidden,
        workflow: section === "process" ? "library" : "intake",
        run_extraction: runExtraction,
        extract_mode: extractMode,
        extraction_policy: extractionPolicy,
        synthesizer_name: synthesize ? effectiveSynthesizer || null : null,
        build_embeddings: embed,
        chunking_method: chunkingMethod,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        enricher_name: enrich
          ? selectedEnricher ||
            readiness.data?.defaults.enricher ||
            "local.stats-keywords"
          : null,
        expert_context: expertContext.trim() || null,
        collection:
          section === "add" && createCollection
            ? {
                name: collectionName.trim(),
                description: collectionDescription.trim() || null,
              }
            : undefined,
      });
      const collectionMessage = run.collection
        ? ` A logical collection, “${run.collection.name}”, will include each document that finishes.`
        : "";
      setNotice({
        severity: "success",
        text: `${section === "process" ? "Processing" : "Intake"} run ${run.id} is queued for ${run.resolved_count ?? preview.data.preview.matched_count} file(s).${collectionMessage}`,
      });
      setUploadedItems([]);
      setExcludedPaths([]);
      setExpertContext("");
      setCreateCollection(false);
      setCollectionName("");
      setCollectionDescription("");
      await queryClient.invalidateQueries({ queryKey: ["processing-runs"] });
      setSelectedLogRunId(run.id);
      setSection("activity");
    } catch (error) {
      setNotice({
        severity: "error",
        text:
          error instanceof Error ? error.message : "Could not start intake.",
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
    setNotice(null);
    if (next === "add") {
      applyIntakePreset(intakePreset);
    } else if (next === "process") {
      chooseLibraryGoal(libraryGoal);
    }
  };

  const matchedCount = preview.data?.preview.matched_count ?? 0;
  const queuedDocumentCount =
    section === "process"
      ? (preview.data?.preview.processing_plan?.unique_document_count ??
        matchedCount)
      : matchedCount;
  const embeddingStatus =
    readiness.data?.embedders.find(
      (embedder) => embedder.id === readiness.data?.defaults.embedder,
    );
  const embeddingAvailable = Boolean(embeddingStatus?.available && !embeddingStatus.lexical && embeddingStatus.id !== "local.hashing");
  const extractorStatus = (name: string) =>
    readiness.data?.extractors.find(
      (extractor) => extractor.id === name || extractor.aliases?.includes(name),
    );
  const unavailableExtractorPlan =
    preview.data?.preview.extractor_plan.filter(
      (plan) =>
        ![plan.extractor, ...(plan.fallbacks ?? [])].some(
          (name) => extractorStatus(name)?.available,
        ),
    ) ?? [];
  const extractorPlanReady =
    Boolean(readiness.data) && unavailableExtractorPlan.length === 0;
  const availableFiles =
    preview.data?.preview.available_files ?? preview.data?.resolved_files ?? [];
  const documentLabel = (filePath: string, display: string) => {
    const upload = uploadedItems.find((item) => item.path === filePath);
    if (upload) return `Uploads/${upload.name}`;
    const root = selectedFolder?.current_path
      .replace(/\\/g, "/")
      .replace(/\/$/, "");
    const normalized = filePath.replace(/\\/g, "/");
    return root && normalized.startsWith(`${root}/`)
      ? normalized.slice(root.length + 1)
      : display;
  };
  const processingSummary =
    [
      runExtraction ? "Read text" : null,
      synthesize
        ? effectiveSynthesizer === "local.extractive-preview"
          ? "Cited source previews"
          : "Summaries"
        : null,
      embed ? "Retrieval embeddings" : null,
      enrich ? "Enrichment" : null,
    ]
      .filter(Boolean)
      .join(" · ") || "No processing selected";

  const followWorkflowStep = (step: WorkflowStepId) => {
    if (["embedding", "language", "extractor"].includes(step)) {
      navigate(`/admin/processors?step=${step}`);
    } else if (step === "index") {
      setSection("process");
      setLibraryGoal("embed");
      chooseLibraryGoal("embed");
    } else {
      changeSection("add");
    }
  };

  const useTextOnlyIntake = () => {
    changeSection("add");
    setIntakePreset("text");
    setRunExtraction(true); setSynthesize(false); setEmbed(false); setEnrich(false);
    setNotice({ severity: "info", text: "Text-only intake selected explicitly. Browsing and keyword search can work after extraction; semantic search and AI chat still need the remaining checkpoints." });
  };

  return (
    <Stack spacing={2.5} sx={{ maxWidth: 1100, mx: "auto" }}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>
          Intake
        </Typography>
        <Typography color="text.secondary">
          Choose a folder and start with the defaults. OSII never changes your
          original files.
        </Typography>
      </Stack>

      <WorkflowProgress readiness={readiness.data} checking={readiness.isLoading} failed={readiness.isError} sourceReady={Boolean((selectedFolder || uploadedItems.length) && !folderChanged && !selectingFolder && !folderError && sourceStatus?.osii_writable !== false)} onStep={followWorkflowStep} />
      {readiness.data && (!embeddingAvailable || !readiness.data.language_model?.available) && section !== "activity" ? <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}><Typography variant="body2" color="text.secondary">Finish model setup for the full experience, or choose a deliberate first pass.</Typography><Button variant="outlined" sx={{ flexShrink: 0 }} onClick={useTextOnlyIntake}>Use text-only intake</Button></Stack> : null}

      <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
        <IntakeSections value={section} onChange={changeSection} />
      </Box>

                      {section === "add" && <TextField select size="small" label="Intake preset" value={intakePreset} disabled={!intakeDefaults.data} onChange={e => applyIntakePreset(e.target.value)} helperText="Choose a starting point, then adjust individual steps below.">
                        {(intakeDefaults.data?.presets ?? [{ id: "summary-search", label: "Loading intake defaults…" }]).map(preset => <MenuItem key={preset.id} value={preset.id}>{preset.label}</MenuItem>)}
                      </TextField>}

      {notice ? <Alert severity={notice.severity}>{notice.text}</Alert> : null}

      {runs.data?.worker && !runs.data.worker.available ? (
        <Alert
          severity="error"
          action={
            <Stack direction="row" spacing={0.5}>
              <Button
                color="inherit"
                size="small"
                onClick={() => setSection("activity")}
              >
                View activity
              </Button>
              <Button
                color="inherit"
                size="small"
                disabled={recoveringQueue}
                onClick={() => void recoverQueue()}
              >
                {recoveringQueue ? "Checking…" : "Recover queue"}
              </Button>
            </Stack>
          }
        >
          <strong>The intake worker is not responding.</strong>{" "}
          {runs.data.worker.detail} New work will remain queued until the worker
          is running.
        </Alert>
      ) : null}

      {section !== "activity" ? (
        <>
          {section === "process" ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stack spacing={1.5}>
                <Stack spacing={0.25}>
                  <Typography fontWeight={700}>
                    What would you like to add or improve?
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    OSII reuses the current primary extraction unless you
                    explicitly upgrade it.
                  </Typography>
                </Stack>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {(
                    [
                      ["embed", "Add embeddings"],
                      ["synthesize", "Generate summaries"],
                      ["reextract", "Upgrade extraction"],
                      ["enrich", "Run enrichment"],
                      ["custom", "Custom workflow"],
                    ] as const
                  ).map(([value, label]) => (
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
                    The new extraction is saved as an immutable version. Making
                    it primary changes what future chunking, embeddings,
                    summaries, and enrichments use; the previous version remains
                    available.
                  </Alert>
                ) : null}
              </Stack>
            </Paper>
          ) : null}

          <Paper
            variant="outlined"
            sx={{
              p: { xs: 2, sm: 3 },
              borderRadius: 2,
              borderColor: "secondary.main",
              borderTopWidth: 4,
            }}
          >
            <Stack spacing={2}>
              <Stack spacing={0.5}>
                <Typography variant="h6" fontWeight={750}>
                  Documents to process
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Choose a folder. All matching files are included
                  automatically; uncheck only the files you want to leave out.
                </Typography>
              </Stack>
              <Box
                component="form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void selectFolder(path);
                }}
              >
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1}
                  alignItems={{ sm: "flex-start" }}
                >
                  <TextField
                    fullWidth
                    label="Document folder"
                    value={path}
                    onChange={(event) => {
                      setPath(event.target.value);
                      setFolderError(null);
                    }}
                    placeholder="Paste a folder path"
                    helperText={
                      folderChanged || !selectedFolder
                        ? "Select Use folder to apply this location."
                        : "This folder is selected. Originals stay where they are."
                    }
                  />
                  <Button
                    type="submit"
                    variant={folderChanged ? "contained" : "outlined"}
                    color="secondary"
                    disabled={selectingFolder || !path.trim()}
                    sx={{ minHeight: 40, flexShrink: 0 }}
                  >
                    {selectingFolder ? "Opening…" : "Use folder"}
                  </Button>
                  <Button
                    variant="outlined"
                    color="secondary"
                    startIcon={<FolderOutlinedIcon />}
                    sx={{ minHeight: 40, flexShrink: 0 }}
                    onClick={() => {
                      setBrowsePath(selectedFolder?.current_path ?? "");
                      setFolderError(null);
                      setBrowseOpen(true);
                    }}
                  >
                    Browse
                  </Button>
                </Stack>
              </Box>
              {folderError && !browseOpen ? (
                <Alert severity="error">{folderError}</Alert>
              ) : null}
              {rootBrowse.isError && !selectedFolder && !folderError ? (
                <Alert severity="error">
                  {rootBrowse.error instanceof Error
                    ? rootBrowse.error.message
                    : "The default folder is unavailable. Choose another folder above."}
                </Alert>
              ) : null}
              {sourceStatus?.osii_writable === false ? (
                <Alert severity="error">
                  OSII's artifact folder is not writable. Fix its access before
                  starting a run.
                </Alert>
              ) : null}

              <Stack spacing={1}>
                <Typography variant="body2" fontWeight={700}>
                  File filters
                </Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                  <TextField
                    select
                    size="small"
                    label="File types"
                    value={filterPreset}
                    onChange={(event) => setFilterPreset(event.target.value)}
                    sx={{ minWidth: { xs: 0, sm: 220 }, width: { xs: "100%", sm: "auto" } }}
                  >
                    {FILE_FILTERS.map((option) => (
                      <MenuItem key={option.value} value={option.value}>
                        {option.label}
                      </MenuItem>
                    ))}
                  </TextField>
                </Stack>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                  <TextField
                    fullWidth
                    size="small"
                    label="Include patterns (optional)"
                    value={includePatterns}
                    onChange={(event) => {
                      setCustomIncludes(event.target.value);
                      setFilterPreset("custom");
                    }}
                    placeholder={"*.pdf\nreports/*.csv"}
                    helperText="One wildcard pattern per line. Blank includes all files; File types fills these patterns."
                    multiline
                    maxRows={4}
                  />
                  <TextField
                    fullWidth
                    size="small"
                    label="Exclude patterns (optional)"
                    value={excludePatterns}
                    onChange={(event) => setExcludePatterns(event.target.value)}
                    placeholder={"*.tmp\narchive/**"}
                    helperText="One wildcard pattern per line. Exclusions take priority over includes."
                    multiline
                    maxRows={4}
                  />
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  Patterns apply to the selected folder and added uploads.
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={includeSubfolders}
                        onChange={(event) =>
                          setIncludeSubfolders(event.target.checked)
                        }
                      />
                    }
                    label="Include subfolders"
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={showHidden}
                        onChange={(event) =>
                          setShowHidden(event.target.checked)
                        }
                      />
                    }
                    label="Include hidden files"
                  />
                </Stack>
              </Stack>

              <Divider />
              <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                spacing={1}
              >
                <Typography fontWeight={700}>
                  {preview.isFetching
                    ? "Updating file selection…"
                    : `${matchedCount} file${matchedCount === 1 ? "" : "s"} included`}
                </Typography>
                {excludedPaths.length ? (
                  <Button size="small" onClick={() => setExcludedPaths([])}>
                    Include all
                  </Button>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    All matching files selected
                  </Typography>
                )}
              </Stack>
              {preview.isFetching || rootBrowse.isLoading || selectingFolder ? (
                <LinearProgress />
              ) : null}
              {preview.isError ? (
                <Alert severity="error">
                  {preview.error instanceof Error
                    ? preview.error.message
                    : "Could not list files for this folder."}
                </Alert>
              ) : null}
              <FileSelectionList files={availableFiles.slice(0, visibleFileCount).map(file => ({ path: file.path, display: documentLabel(file.path, file.display), size_bytes: "size_bytes" in file && typeof file.size_bytes === "number" ? file.size_bytes : null }))} excludedPaths={excludedPaths}
                onToggle={path => setExcludedPaths(paths => paths.includes(path) ? paths.filter(item => item !== path) : [...paths, path])} />
              {availableFiles.length > visibleFileCount ? (
                <Button
                  sx={{ alignSelf: "flex-start" }}
                  onClick={() => setVisibleFileCount((count) => count + 50)}
                >
                  Show more files ({availableFiles.length - visibleFileCount}{" "}
                  remaining)
                </Button>
              ) : null}
              {preview.data && !availableFiles.length ? (
                <Typography variant="body2" color="text.secondary">
                  No files match. Check the folder and filters, or add files
                  below.
                </Typography>
              ) : null}
              <Stack
                direction={{ xs: "column", sm: "row" }}
                justifyContent="space-between"
                alignItems={{ sm: "center" }}
                spacing={1}
              >
                <Typography variant="caption" color="text.secondary">
                  {preview.data
                    ? `${preview.data.preview.unprocessed_count} new · ${preview.data.preview.processed_count} already read · ${preview.data.preview.total_size_human}`
                    : "Files already read by OSII keep their existing extraction by default."}
                </Typography>
                {section === "add" ? (
                  <Button
                    component="label"
                    variant="text"
                    startIcon={<UploadFileOutlinedIcon />}
                    disabled={uploading}
                  >
                    {uploading ? "Uploading…" : "Add files from elsewhere"}
                    <input
                      hidden
                      type="file"
                      multiple
                      onChange={handleUpload}
                    />
                  </Button>
                ) : null}
              </Stack>
              {uploadedItems.length ? (
                <Typography variant="caption" color="text.secondary">
                  {uploadedItems.length} uploaded file(s) added alongside the
                  folder. Uploaded files follow the same filters.
                </Typography>
              ) : null}
            </Stack>
          </Paper>

          <Dialog
            open={browseOpen}
            onClose={() => {
              setBrowseOpen(false);
              setFolderError(null);
            }}
            fullWidth
            maxWidth="sm"
          >
            <DialogTitle>Choose a document folder</DialogTitle>
            <DialogContent>
              <Stack spacing={1.5} sx={{ pt: 1 }}>
                <Box
                  component="form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    setFolderError(null);
                    setBrowsePath(browseAddress);
                  }}
                >
                  <Stack direction="row" spacing={1}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Folder path"
                      value={browseAddress}
                      onChange={(event) => setBrowseAddress(event.target.value)}
                    />
                    <Button type="submit" variant="outlined">
                      Go
                    </Button>
                  </Stack>
                </Box>
                <Stack direction="row" spacing={1}>
                  <Button
                    disabled={!browse.data?.parent_path || browse.isFetching}
                    onClick={() =>
                      setBrowsePath(browse.data?.parent_path ?? "")
                    }
                  >
                    Up one folder
                  </Button>
                  <Button onClick={() => setBrowsePath("")}>
                    Default folder
                  </Button>
                </Stack>
                {browse.isFetching ? <LinearProgress /> : null}
                {browse.isError ? (
                  <Alert severity="error">
                    {browse.error instanceof Error
                      ? browse.error.message
                      : "Could not open this folder."}
                  </Alert>
                ) : null}
                {folderError ? (
                  <Alert severity="error">{folderError}</Alert>
                ) : null}
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ overflowWrap: "anywhere" }}
                >
                  {browse.data?.host_path ?? browse.data?.current_path}
                </Typography>
                <List
                  dense
                  aria-label="Available folders"
                  sx={{ maxHeight: 320, overflow: "auto" }}
                >
                  {(browse.data?.entries ?? [])
                    .filter((entry) => entry.type === "folder")
                    .map((entry) => (
                      <ListItem key={entry.path} disablePadding>
                        <ListItemButton
                          onClick={() => setBrowsePath(entry.path)}
                        >
                          <FolderOutlinedIcon sx={{ mr: 1 }} />
                          <ListItemText primary={entry.name} />
                        </ListItemButton>
                      </ListItem>
                    ))}
                </List>
                {browse.data &&
                !browse.data.entries.some(
                  (entry) => entry.type === "folder",
                ) ? (
                  <Typography variant="body2" color="text.secondary">
                    No subfolders. You can use this folder.
                  </Typography>
                ) : null}
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button
                onClick={() => {
                  setBrowseOpen(false);
                  setFolderError(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="contained"
                color="secondary"
                disabled={
                  !browse.data ||
                  browse.isFetching ||
                  browse.isError ||
                  selectingFolder
                }
                onClick={() =>
                  void selectFolder(browse.data?.current_path ?? "")
                }
              >
                Use this folder
              </Button>
            </DialogActions>
          </Dialog>

          <Accordion
            variant="outlined"
            disableGutters
            sx={{
              borderRadius: "8px !important",
              "&:before": { display: "none" },
            }}
          >
            <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
              <Stack>
                <Typography fontWeight={700}>
                  Change processing options
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {processingSummary}. The configured defaults are already
                  selected.
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2.5}>
                {section === "add" ? (
                  <Stack spacing={1}>
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={createCollection}
                          onChange={(event) =>
                            setCreateCollection(event.target.checked)
                          }
                        />
                      }
                      label="Save this run as a reusable collection"
                    />
                    {createCollection ? (
                      <>
                        <TextField
                          fullWidth
                          size="small"
                          label="Collection name"
                          value={collectionName}
                          required
                          onChange={(event) =>
                            setCollectionName(event.target.value)
                          }
                        />
                        <TextField
                          fullWidth
                          size="small"
                          label="Collection description (optional)"
                          value={collectionDescription}
                          onChange={(event) =>
                            setCollectionDescription(event.target.value)
                          }
                        />
                      </>
                    ) : null}
                  </Stack>
                ) : null}
                <TextField
                  fullWidth
                  multiline
                  minRows={2}
                  label="Expert context (optional)"
                  value={expertContext}
                  onChange={(event) => setExpertContext(event.target.value)}
                  inputProps={{ maxLength: 20_000 }}
                  helperText="Guidance saved with selected documents for model-backed extraction, synthesis, and enrichment. Leave blank to reuse saved context. Tesseract does not use it."
                />
                <Box>
                  <Stack spacing={1.5}>
                    <Stack spacing={0.25}>
                      <Typography fontWeight={700}>Processing steps</Typography>
                      {intakeDefaults.isError && <Alert severity="error">Could not load intake defaults: {intakeDefaults.error.message}</Alert>}
                      <Typography variant="body2" color="text.secondary">
                        {section === "process"
                          ? "Only the selected steps run. Downstream work uses each document's current primary extraction."
                          : "New documents receive a primary extraction. These optional steps create additional representations."}
                      </Typography>
                    </Stack>
                    {section === "process" &&
                    (libraryGoal === "reextract" ||
                      libraryGoal === "custom") ? (
                      <Stack spacing={1}>
                        <FormControlLabel
                          control={
                            <Checkbox
                              checked={runExtraction}
                              onChange={(event) =>
                                setRunExtraction(event.target.checked)
                              }
                            />
                          }
                          label="Run extraction"
                        />
                        {runExtraction ? (
                          <TextField
                            select
                            size="small"
                            label="After the new extraction finishes"
                            value={extractionPolicy}
                            onChange={(event) =>
                              setExtractionPolicy(
                                event.target.value as typeof extractionPolicy,
                              )
                            }
                          >
                            <MenuItem value="make_primary">
                              Make it primary and preserve the previous version
                            </MenuItem>
                            <MenuItem value="save_variant">
                              Save as another version; keep the current primary
                            </MenuItem>
                          </TextField>
                        ) : null}
                      </Stack>
                    ) : null}
                    <ProcessorStepControl label="Generate document summaries" methodLabel="Synthesizer" checked={synthesize} onChecked={setSynthesize}
                      method={effectiveSynthesizer} onMethod={setSelectedSynthesizer} options={availableSynthesizers}
                      disabled={extractionPolicy === "save_variant" && runExtraction}
                      helperText={!availableSynthesizers.length ? "Summaries are unavailable until a synthesizer is connected in Setup. You can still read and search extracted text." : effectiveSynthesizer === "local.extractive-preview" ? "Using the no-AI baseline: OSII copies cited source excerpts and does not generate new prose." : "Using a connected model-backed synthesizer; its provider and model are recorded with the result."} />
                    {embed ? (
                      <Accordion variant="outlined" disableGutters>
                        <AccordionSummary
                          expandIcon={<ExpandMoreOutlinedIcon />}
                        >
                          <Stack spacing={0.2}>
                            <Typography variant="body2" fontWeight={600}>
                              Retrieval chunking
                            </Typography>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
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
                              onChange={(event) =>
                                setChunkingMethod(
                                  event.target.value as ChunkingMethod,
                                )
                              }
                            >
                              <MenuItem value="sentence_window">
                                Sentence-aligned windows (recommended)
                              </MenuItem>
                              <MenuItem value="paragraph">
                                Paragraphs (compatibility)
                              </MenuItem>
                              <MenuItem value="window">
                                Fixed character windows
                              </MenuItem>
                            </TextField>
                            {chunkingMethod !== "paragraph" ? (
                              <Stack
                                direction={{ xs: "column", sm: "row" }}
                                spacing={1.5}
                              >
                                <TextField
                                  size="small"
                                  type="number"
                                  label="Maximum characters"
                                  value={chunkSize}
                                  inputProps={{ min: 100, step: 100 }}
                                  onChange={(event) =>
                                    setChunkSize(Number(event.target.value))
                                  }
                                />
                                <TextField
                                  size="small"
                                  type="number"
                                  label="Overlap characters"
                                  value={chunkOverlap}
                                  inputProps={{ min: 0, step: 25 }}
                                  error={!chunkSettingsValid}
                                  helperText={
                                    !chunkSettingsValid
                                      ? "Overlap must be smaller than the chunk size."
                                      : "Preserves context across boundaries."
                                  }
                                  onChange={(event) =>
                                    setChunkOverlap(Number(event.target.value))
                                  }
                                />
                              </Stack>
                            ) : null}
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              Sentence-aligned windows preserve exact character
                              offsets and source-page grounding. Changing these
                              settings rebuilds both semantic and BM25 indexes.
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
                      control={
                        <Checkbox
                          checked={embed}
                          disabled={
                            (!embeddingAvailable && !embed) ||
                            (extractionPolicy === "save_variant" &&
                              runExtraction)
                          }
                          onChange={(event) => setEmbed(event.target.checked)}
                        />
                      }
                      label="Build retrieval embeddings"
                    />
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: -1 }}
                    >
                      {embeddingAvailable
                        ? `Ready${embeddingStatus?.model ? `: ${embeddingStatus.model}` : ""}.${embeddingStatus?.lexical ? " Hashing vectors provide approximate lexical similarity, not semantic understanding." : ""}`
                        : "Unavailable and cannot be queued. Lexical search remains available without an embedder."}
                    </Typography>
                    {section === "process" &&
                    (libraryGoal === "enrich" || libraryGoal === "custom") ? (
                      <>
                        <ProcessorStepControl label="Run enrichment" methodLabel="Enricher" checked={enrich} onChecked={setEnrich}
                          method={selectedEnricher || readiness.data?.defaults.enricher || ""} onMethod={setSelectedEnricher}
                          options={(readiness.data?.enrichers ?? []).filter(item => item.available)} disabled={extractionPolicy === "save_variant" && runExtraction} />
                      </>
                    ) : null}
                    {extractionPolicy === "save_variant" && runExtraction ? (
                      <Alert severity="info">
                        Downstream steps are disabled because this new
                        extraction will not become primary.
                      </Alert>
                    ) : null}
                  </Stack>
                </Box>
                <Divider />
                <Stack spacing={1}>
                  <Typography variant="body2" fontWeight={700}>
                    Repair moved source paths
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Checks the launcher's default document folder for previously
                    processed files moved within it. It does not select files
                    for this run.
                  </Typography>
                  <Button
                    startIcon={<RefreshOutlinedIcon />}
                    disabled={rescanning}
                    onClick={() => void rescanSources(false)}
                    sx={{ alignSelf: "flex-start" }}
                  >
                    Check moved files
                  </Button>
                  {rescanResult ? (
                    <Typography variant="body2">
                      {rescanResult.summary.moved} moved
                    </Typography>
                  ) : null}
                  {rescanResult?.summary.moved ? (
                    <Button
                      disabled={rescanning}
                      onClick={() => void rescanSources(true)}
                      sx={{ alignSelf: "flex-start" }}
                    >
                      Apply hash-matched repairs
                    </Button>
                  ) : null}
                </Stack>
              </Stack>
            </AccordionDetails>
          </Accordion>

          <Box sx={{ px: { xs: 0, sm: 1 }, py: 1 }}>
            <Stack spacing={1.5}>
              <Stack spacing={0.25}>
                <Typography variant="h6" fontWeight={700}>
                  Ready to start
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Review exactly what will run before adding it to the
                  sequential processing queue.
                </Typography>
              </Stack>

              {preview.isLoading || rootBrowse.isLoading ? (
                <LinearProgress />
              ) : null}
              {preview.isError ? (
                <Alert severity="error">
                  Could not preview this intake.
                  {preview.error instanceof Error
                    ? ` ${preview.error.message}`
                    : ""}
                </Alert>
              ) : null}

              {expertContext.trim() ? (
                <Paper
                  variant="outlined"
                  sx={{ p: 1.5, bgcolor: "action.hover" }}
                >
                  <Stack spacing={0.5}>
                    <Typography
                      variant="caption"
                      fontWeight={700}
                      color="text.secondary"
                    >
                      EXPERT CONTEXT INCLUDED
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                      {expertContext.trim()}
                    </Typography>
                  </Stack>
                </Paper>
              ) : null}

              {preview.data?.preview.processing_plan ? (
                <Stack spacing={0.75}>
                  {preview.data.preview.processing_plan.steps.map((step) => (
                    <Stack
                      key={step.id}
                      direction="row"
                      justifyContent="space-between"
                      spacing={2}
                    >
                      <Typography variant="body2">{step.label}</Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {step.eligible_count} queued
                        {step.current_count
                          ? ` · ${step.current_count} already current`
                          : ""}
                      </Typography>
                    </Stack>
                  ))}
                  {preview.data.preview.processing_plan.blocked_count ? (
                    <Alert severity="warning">
                      {preview.data.preview.processing_plan.blocked_count}{" "}
                      document(s) have no extraction and will be skipped unless
                      extraction is selected.
                    </Alert>
                  ) : null}
                </Stack>
              ) : null}

              {!selectedFolder && !uploadedItems.length ? (
                <Alert severity="info">
                  Choose a document folder or add files from elsewhere.
                </Alert>
              ) : null}
              {readiness.isError ? (
                <Alert severity="error">
                  Could not check processing services.{" "}
                  {readiness.error instanceof Error
                    ? readiness.error.message
                    : ""}
                </Alert>
              ) : null}
              {readiness.data && runExtraction && !extractorPlanReady ? (
                <Alert severity="error">
                  An extractor is unavailable for:{" "}
                  {unavailableExtractorPlan
                    .map((item) => item.extension)
                    .join(", ")}
                  . Connect the required processor in Setup or exclude those
                  file types.
                </Alert>
              ) : null}
              {readiness.data && synthesize && !effectiveSynthesizer ? (
                <Alert severity="warning">
                  No synthesizer is connected. Connect one in Setup, or turn off
                  summaries under Change processing options.
                </Alert>
              ) : null}
              {readiness.data && embed && !embeddingAvailable ? <Alert severity="warning" action={<Button color="inherit" onClick={() => navigate("/admin/processors?step=embedding")}>Set up embeddings</Button>}>Semantic embeddings are selected, but the default embedding model is unavailable. {embeddingStatus?.detail} Configure it in Setup or explicitly choose text-only intake above.</Alert> : null}
              {preview.data && matchedCount === 0 ? (
                <Alert severity="warning">
                  No files match the current source scope and intake rules.
                </Alert>
              ) : null}
              {!runExtraction && !synthesize && !embed && !enrich ? (
                <Alert severity="info">Select at least one step under Change processing options.</Alert>
              ) : null}

              <Button
                variant="contained"
                color="secondary"
                startIcon={<PlayArrowOutlinedIcon />}
                disabled={
                  !queuePaths.length ||
                  (!runExtraction && !synthesize && !embed && !enrich) ||
                  !matchedCount ||
                  starting ||
                  preview.isFetching ||
                  filtersUpdating ||
                  preview.isError ||
                  selectingFolder ||
                  folderChanged ||
                  Boolean(folderError) ||
                  readiness.isLoading ||
                  sourceStatus?.osii_writable === false ||
                  runs.data?.worker?.available === false ||
                  (runExtraction && !extractorPlanReady) ||
                  (synthesize && !effectiveSynthesizer) ||
                  (embed && !embeddingAvailable) ||
                  (embed && !chunkSettingsValid) ||
                  (extractionPolicy === "save_variant" &&
                    runExtraction &&
                    (synthesize || embed || enrich)) ||
                  (section === "add" &&
                    createCollection &&
                    !collectionName.trim())
                }
                onClick={() => void start()}
                sx={{ alignSelf: "flex-start" }}
              >
                {starting
                  ? "Queueing work…"
                  : `${section === "process" ? "Queue processing" : "Start intake"}${queuedDocumentCount ? ` (${queuedDocumentCount} document${queuedDocumentCount === 1 ? "" : "s"})` : ""}`}
              </Button>
            </Stack>
          </Box>
        </>
      ) : null}

      {section === "activity" && <ProcessingActivity recentRuns={recentRuns} workerAvailable={runs.data?.worker?.available}
        selectedLogRunId={selectedLogRunId} setSelectedLogRunId={setSelectedLogRunId} controllingRun={controllingRun}
        controlRun={(run, action) => action === "start" ? undefined : controlRun(run, action)} displayedLogLines={displayedLogLines}
        refreshLogs={() => void runLogs.refetch()} logError={runLogs.isError} />}

    </Stack>
  );
}
