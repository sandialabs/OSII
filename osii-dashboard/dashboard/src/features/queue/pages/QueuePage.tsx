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
import AddOutlinedIcon from "@mui/icons-material/AddOutlined";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  browseIntake,
  createProcessingRun,
  listProcessingRuns,
  resolveIntake,
  uploadQueueFiles,
} from "../../../api/queue";
import type {
  QueueBrowseEntry,
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

function parentDisplay(display: string): string {
  const normalized = display.replace(/\\/g, "/");
  const parts = normalized.split("/");
  if (parts.length <= 1) return "Shared root";
  return parts.slice(0, -1).join("/");
}

export function QueuePage() {
  const queryClient = useQueryClient();
  const [path, setPath] = useState("");
  const [includeSharedRoot, setIncludeSharedRoot] = useState(true);
  const [selectedSharedItems, setSelectedSharedItems] = useState<SelectedSharedItem[]>([]);
  const [uploadedItems, setUploadedItems] = useState<UploadResponse["uploads"]>([]);
  const [filterPreset, setFilterPreset] = useState("all");
  const [customIncludes, setCustomIncludes] = useState("");
  const [excludePatterns, setExcludePatterns] = useState("");
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [showHidden, setShowHidden] = useState(false);
  const [synthesize, setSynthesize] = useState(true);
  const [embed, setEmbed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const selectedFilter = FILE_FILTERS.find(
    (option) => option.value === filterPreset,
  ) ?? FILE_FILTERS[0];
  const includePatterns = filterPreset === "custom"
    ? customIncludes
    : selectedFilter.patterns;
  const deferredIncludePatterns = useDeferredValue(includePatterns);
  const deferredExcludePatterns = useDeferredValue(excludePatterns);

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
      (run) => ["queued", "pending", "running"].includes(run.status),
    ) ? 1500 : 5000,
  });

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
    ],
    queryFn: () => resolveIntake({
      queue_paths: queuePaths,
      include_subfolders: includeSubfolders,
      include_patterns: deferredIncludePatterns,
      exclude_patterns: deferredExcludePatterns,
      show_hidden: showHidden,
    }),
    enabled: queuePaths.length > 0,
  });

  const recentRuns = useMemo(
    () => runs.data?.runs.slice(0, 10) ?? [],
    [runs.data],
  );

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
        synthesizer_name: synthesize ? "firstN" : null,
        build_embeddings: embed,
      });
      setNotice({
        severity: "success",
        text: `Intake run ${run.id} is queued for ${run.resolved_count ?? preview.data.preview.matched_count} file(s).`,
      });
      setUploadedItems([]);
      setSelectedSharedItems([]);
      setIncludeSharedRoot(true);
      await queryClient.invalidateQueries({ queryKey: ["processing-runs"] });
    } catch (error) {
      setNotice({
        severity: "error",
        text: error instanceof Error ? error.message : "Could not start intake.",
      });
    } finally {
      setStarting(false);
    }
  };

  const matchedCount = preview.data?.preview.matched_count ?? 0;

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>Intake</Typography>
        <Typography color="text.secondary">
          Bring a shared corpus or one-off uploads into OSII. The shared volume is selected in full by default.
        </Typography>
      </Stack>

      {notice ? <Alert severity={notice.severity}>{notice.text}</Alert> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            justifyContent="space-between"
            spacing={1}
          >
            <Stack spacing={0.25}>
              <Typography fontWeight={700}>1. Shared volume</Typography>
              <Typography variant="body2" color="text.secondary">
                Intake the corpus as a whole. Choose individual paths only when a broad folder selection is not suitable.
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

          <FormControlLabel
            control={(
              <Checkbox
                checked={includeSharedRoot}
                onChange={(event) => setIncludeSharedRoot(event.target.checked)}
              />
            )}
            label="Include the entire shared volume"
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
                    label="Browse folder"
                    value={path}
                    onChange={(event) => setPath(event.target.value)}
                    placeholder="Leave blank for shared root"
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
                    Select folder
                  </Button>
                </Stack>

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

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>2. One-off uploads</Typography>
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
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>3. Filters and outputs</Typography>
            <Typography variant="body2" color="text.secondary">
              Filters apply across the selected folders. Patterns use filename globs, one per line.
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

          <Divider />
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
            <FormControlLabel
              control={(
                <Checkbox
                  checked={synthesize}
                  onChange={(event) => setSynthesize(event.target.checked)}
                />
              )}
              label="Create local text previews"
            />
            <FormControlLabel
              control={(
                <Checkbox
                  checked={embed}
                  onChange={(event) => setEmbed(event.target.checked)}
                />
              )}
              label="Build search embeddings"
            />
            <Typography variant="caption" color="text.secondary">
              Embeddings require a configured embedding service. Lexical search works without one.
            </Typography>
          </Stack>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>4. Review and start</Typography>
            <Typography variant="body2" color="text.secondary">
              Existing files are refreshed so changed source content and derived artifacts stay current.
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

          {!includeSharedRoot && !selectedSharedItems.length && !uploadedItems.length ? (
            <Alert severity="info">
              Select a shared folder/file or upload one-off files.
            </Alert>
          ) : null}
          {preview.data && matchedCount === 0 ? (
            <Alert severity="warning">
              No files match the current selection and filters.
            </Alert>
          ) : null}

          <Button
            variant="contained"
            startIcon={<PlayArrowOutlinedIcon />}
            disabled={!queuePaths.length || !matchedCount || starting || preview.isLoading}
            onClick={() => void start()}
            sx={{ alignSelf: "flex-start" }}
          >
            {starting ? "Starting intake…" : `Start intake${matchedCount ? ` (${matchedCount} files)` : ""}`}
          </Button>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography fontWeight={700}>Recent intake runs</Typography>
          {recentRuns.map((run) => (
            <Paper key={run.id} variant="outlined" sx={{ p: 1.5 }}>
              <Stack
                direction={{ xs: "column", sm: "row" }}
                justifyContent="space-between"
                spacing={1}
              >
                <Stack>
                  <Typography fontWeight={600}>{run.id.slice(0, 12)}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {run.completed ?? 0} / {run.total ?? 0} files · {run.created_at}
                  </Typography>
                </Stack>
                <Chip
                  color={
                    run.status === "done"
                      ? "success"
                      : run.status === "error"
                        ? "error"
                        : "primary"
                  }
                  label={run.status}
                />
              </Stack>
              {run.error ? <Alert severity="error" sx={{ mt: 1 }}>{run.error}</Alert> : null}
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
            </Paper>
          ))}
          {!recentRuns.length ? (
            <Typography color="text.secondary">No intake runs yet.</Typography>
          ) : null}
        </Stack>
      </Paper>
    </Stack>
  );
}
