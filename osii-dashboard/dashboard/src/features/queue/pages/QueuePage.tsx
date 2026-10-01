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
  Chip,
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
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
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
  const [section, setSection] = useState<"add" | "process" | "activity">("add");
  const [libraryGoal, setLibraryGoal] = useState<
    "embed" | "synthesize" | "reextract" | "enrich" | "custom"
  >("embed");
  const [runExtraction, setRunExtraction] = useState(true);
  const [extractMode, setExtractMode] = useState<"missing" | "reprocess">(
    "missing",
  );
  const [extractionPolicy, setExtractionPolicy] = useState<
    "make_primary" | "save_variant"
  >("make_primary");
  const [synthesize, setSynthesize] = useState(true);
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
  const logPanelRef = useRef<HTMLPreElement | null>(null);

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

  useEffect(() => {
    const panel = logPanelRef.current;
    if (panel) panel.scrollTop = panel.scrollHeight;
  }, [displayedLogLines.length, selectedLogRunId]);

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
      setRunExtraction(true); setExtractMode("missing"); setExtractionPolicy("make_primary");
      setSynthesize(true); setEmbed(true); setEnrich(false);
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
    ) ?? readiness.data?.embedders[0];
  const embeddingAvailable = Boolean(embeddingStatus?.available);
  useEffect(() => {
    if (section === "add" && readiness.data && !embeddingAvailable && embed) {
      setEmbed(false);
    }
  }, [section, readiness.data, embeddingAvailable, embed]);
  useEffect(() => {
    if (
      section === "add" &&
      readiness.data &&
      !availableSynthesizers.length &&
      synthesize
    ) {
      setSynthesize(false);
    }
  }, [section, readiness.data, availableSynthesizers.length, synthesize]);
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

      <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
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
      </Box>

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
                  <TextField
                    fullWidth
                    size="small"
                    label="Exclude patterns (optional)"
                    value={excludePatterns}
                    onChange={(event) => setExcludePatterns(event.target.value)}
                    placeholder={"*.tmp\narchive/**"}
                    helperText="One wildcard pattern per line, for example *.tmp or archive/**."
                    multiline
                    maxRows={4}
                  />
                </Stack>
                {filterPreset === "custom" ? (
                  <TextField
                    fullWidth
                    size="small"
                    label="Include patterns"
                    value={customIncludes}
                    onChange={(event) => setCustomIncludes(event.target.value)}
                    placeholder={"*.pdf\nreports/**/*.csv"}
                    multiline
                    maxRows={4}
                    helperText="One wildcard pattern per line. These rules apply to the folder and uploads."
                  />
                ) : null}
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
              <List
                dense
                sx={{
                  maxHeight: 300,
                  overflow: "auto",
                  bgcolor: "action.hover",
                  borderRadius: 1,
                }}
                aria-label="Files included in this run"
              >
                {availableFiles.slice(0, visibleFileCount).map((file) => (
                  <ListItem key={file.path} disablePadding>
                    <ListItemButton
                      onClick={() =>
                        setExcludedPaths((paths) =>
                          paths.includes(file.path)
                            ? paths.filter((item) => item !== file.path)
                            : [...paths, file.path],
                        )
                      }
                    >
                      <Checkbox
                        edge="start"
                        checked={!excludedPaths.includes(file.path)}
                        tabIndex={-1}
                        disableRipple
                        inputProps={{
                          "aria-label": `Include ${documentLabel(file.path, file.display)}`,
                        }}
                      />
                      <ListItemText
                        primary={documentLabel(file.path, file.display)}
                        secondary={
                          "size_bytes" in file &&
                          typeof file.size_bytes === "number"
                            ? formatSize(file.size_bytes)
                            : undefined
                        }
                        primaryTypographyProps={{
                          variant: "body2",
                          sx: { overflowWrap: "anywhere" },
                        }}
                      />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
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
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={synthesize}
                          disabled={
                            !availableSynthesizers.length ||
                            (extractionPolicy === "save_variant" &&
                              runExtraction)
                          }
                          onChange={(event) =>
                            setSynthesize(event.target.checked)
                          }
                        />
                      }
                      label="Generate document summaries"
                    />
                    {synthesize ? (
                      <TextField
                        select
                        size="small"
                        label="Synthesizer"
                        value={effectiveSynthesizer}
                        onChange={(event) =>
                          setSelectedSynthesizer(event.target.value)
                        }
                      >
                        {availableSynthesizers.map((item) => (
                          <MenuItem key={item.id} value={item.id}>
                            {item.display_name}
                          </MenuItem>
                        ))}
                      </TextField>
                    ) : null}
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: -1 }}
                    >
                      {!availableSynthesizers.length
                        ? "Summaries are unavailable until a synthesizer is connected in Setup. You can still read and search extracted text."
                        : effectiveSynthesizer === "local.extractive-preview"
                          ? "Using the no-AI baseline: OSII copies cited source excerpts and does not generate new prose."
                          : "Using a connected model-backed synthesizer; its provider and model are recorded with the result."}
                    </Typography>
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
                        <FormControlLabel
                          control={
                            <Checkbox
                              checked={enrich}
                              disabled={
                                extractionPolicy === "save_variant" &&
                                runExtraction
                              }
                              onChange={(event) =>
                                setEnrich(event.target.checked)
                              }
                            />
                          }
                          label="Run enrichment"
                        />
                        {enrich ? (
                          <TextField
                            select
                            size="small"
                            label="Enricher"
                            value={
                              selectedEnricher ||
                              readiness.data?.defaults.enricher ||
                              ""
                            }
                            onChange={(event) =>
                              setSelectedEnricher(event.target.value)
                            }
                          >
                            {(readiness.data?.enrichers ?? [])
                              .filter((item) => item.available)
                              .map((item) => (
                                <MenuItem key={item.id} value={item.id}>
                                  {item.display_name}
                                </MenuItem>
                              ))}
                          </TextField>
                        ) : null}
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

      {section === "activity" ? <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1} alignItems={{ sm: "center" }}>
            <Typography fontWeight={700}>Processing activity</Typography>
            <Chip
              size="small"
              color={runs.data?.worker?.available ? "success" : "error"}
              label={runs.data?.worker?.available ? "Worker responding" : "Worker unavailable"}
            />
          </Stack>
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
            const itemErrors = (run.items ?? []).filter((item) => item.error);
            const controllable = Boolean(run.workflow);
            const canPause = controllable && ["queued", "pending", "running"].includes(run.status);
            const canResume = controllable && run.status === "paused";
            const canCancel = controllable && ["queued", "pending", "running", "pausing", "paused"].includes(run.status);
            const canRetry = controllable && run.status === "error";
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
                  <Button
                    size="small"
                    variant={selectedLogRunId === run.id ? "contained" : "text"}
                    onClick={() => setSelectedLogRunId(run.id)}
                  >
                    View log
                  </Button>
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
                  {canRetry ? (
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<RefreshOutlinedIcon />}
                      disabled={controllingRun !== null || runs.data?.worker?.available === false}
                      onClick={() => void controlRun(run, "retry")}
                    >
                      Retry failed run
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
              {itemErrors.length ? (
                <Alert severity="error" sx={{ mt: 1 }}>
                  {itemErrors.slice(0, 3).map((item, index) => (
                    <Typography key={`${item.display}-${index}`} variant="body2">
                      {item.display}: {item.error}
                    </Typography>
                  ))}
                  {itemErrors.length > 3 ? `And ${itemErrors.length - 3} more file error(s).` : null}
                </Alert>
              ) : null}
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
          {selectedLogRunId ? (
            <Paper
              variant="outlined"
              sx={{
                bgcolor: "#10151d",
                color: "#d8e2ef",
                borderColor: "#344155",
                overflow: "hidden",
              }}
            >
              <Stack
                direction={{ xs: "column", sm: "row" }}
                justifyContent="space-between"
                alignItems={{ sm: "center" }}
                spacing={1}
                sx={{ px: 1.5, py: 1, borderBottom: "1px solid #344155" }}
              >
                <Typography variant="body2" fontWeight={700} color="inherit">
                  Live run log · {selectedLogRunId.slice(0, 8)}
                  {selectedLogRun ? ` · ${selectedLogRun.status}` : ""}
                </Typography>
                <Stack direction="row" spacing={1}>
                  <Button size="small" color="inherit" onClick={() => void runLogs.refetch()}>
                    Refresh
                  </Button>
                </Stack>
              </Stack>
              <Box
                component="pre"
                ref={logPanelRef}
                aria-live="polite"
                sx={{
                  m: 0,
                  p: 1.5,
                  minHeight: 120,
                  maxHeight: 300,
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                  fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                  fontSize: "0.78rem",
                  lineHeight: 1.55,
                }}
              >
                {runLogs.isError
                  ? "Could not load this run log. Use Refresh after confirming the backend is available."
                  : displayedLogLines.join("\n")
                    || "Waiting for the worker to begin this run…"}
              </Box>
            </Paper>
          ) : null}
          {!recentRuns.length ? (
            <Typography color="text.secondary">No intake runs yet.</Typography>
          ) : null}
        </Stack>
      </Paper> : null}
    </Stack>
  );
}
