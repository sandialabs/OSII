import { ChangeEvent, useDeferredValue, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
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
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import { apiJson } from "../../../api/client";
import { uploadQueueFiles } from "../../../api/queue";
import {
  LocationBrowser,
  type PickedFile,
} from "../../../components/discovery/LocationBrowser";
import { ScanCard, type Scan, type Source } from "./DiscoveryActivity";

type Entry = {
  id: number;
  path: string;
  size_bytes: number | null;
  metadata_state: string;
  metadata_error: string | null;
  scan_run_id: number | null;
};
type Selection = {
  id: number;
  count: number;
  bytes: number;
  coverage: string;
  request: string;
  created: number;
};
const bytes = (n: number) =>
  n < 1024 ** 2
    ? `${(n / 1024).toFixed(1)} KiB`
    : n < 1024 ** 3
      ? `${(n / 1024 ** 2).toFixed(1)} MiB`
      : `${(n / 1024 ** 3).toFixed(1)} GiB`;
const lines = (value: string) =>
  value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
const normalize = (path: string) =>
  path.replace(/\\/g, "/").replace(/\/+$/, "");
export function DiscoveryIntakePanel({
  selectedId,
  onSelect,
  directFiles,
  onFiles,
}: {
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  directFiles: PickedFile[];
  onFiles: (files: PickedFile[]) => void;
}) {
  const client = useQueryClient();
  const [sourceId, setSourceId] = useState<number | "">("");
  const [adding, setAdding] = useState(false);
  const [root, setRoot] = useState("");
  const [folderBrowser, setFolderBrowser] = useState(false);
  const [fileBrowser, setFileBrowser] = useState(false);
  const [showEntries, setShowEntries] = useState(false);
  const [matching, setMatching] = useState(false);
  const [review, setReview] = useState(false);
  const [saved, setSaved] = useState(false);
  const [include, setInclude] = useState("");
  const [exclude, setExclude] = useState("");
  const [depth, setDepth] = useState("");
  const [readers, setReaders] = useState(2);
  const [hidden, setHidden] = useState(false);
  const [cross, setCross] = useState(false);
  const [name, setName] = useState("");
  const [suffix, setSuffix] = useState("");
  const [prefix, setPrefix] = useState("");
  const [prior, setPrior] = useState("any");
  const [metadata, setMetadata] = useState("known");
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [minSize, setMinSize] = useState("");
  const [maxSize, setMaxSize] = useState("50");
  const [maxFiles, setMaxFiles] = useState(100);
  const [budget, setBudget] = useState(1024);
  const [partial, setPartial] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [previous, setPrevious] = useState<number[]>([]);
  const [frozenCursor, setFrozenCursor] = useState(0);
  const [draft, setDraft] = useState<Map<number, Entry>>(new Map());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locationNotice, setLocationNotice] = useState<string | null>(null);
  const [mountIssue, setMountIssue] = useState(false);
  const [verified, setVerified] = useState(false);
  const [confirmRoot, setConfirmRoot] = useState("");
  const sources = useQuery({
    queryKey: ["discovery", "sources"],
    queryFn: () => apiJson<{ items: Source[] }>("/api/volume/sources"),
  });
  const runs = useQuery({
    queryKey: ["discovery", "source-scans", sourceId],
    queryFn: async () =>
      (
        await apiJson<{ items: Scan[] }>(
          `/api/volume/sources/${sourceId}/scans`,
        )
      ).items,
    enabled: sourceId !== "",
    refetchInterval: 3000,
  });
  const source = sources.data?.items.find((item) => item.id === sourceId);
  const latest = runs.data?.find((run) => run.source_id === sourceId);
  const selected = useQuery({
    queryKey: ["discovery", "selection", selectedId],
    queryFn: () => apiJson<Selection>(`/api/volume/selections/${selectedId}`),
    enabled: selectedId !== null,
  });
  useEffect(() => {
    if (selected.data)
      setSourceId(JSON.parse(selected.data.request).filters.source_id);
  }, [selected.data]);
  useEffect(() => {
    if (sourceId === "" && sources.data?.items.length)
      setSourceId(
        (
          sources.data.items.find(
            (item) =>
              item.root === localStorage.getItem("osii:last-discovery-root"),
          ) ?? sources.data.items[0]
        ).id,
      );
  }, [sources.data, sourceId]);
  useEffect(() => {
    if (
      latest?.issue_code === "identity_changed" ||
      latest?.error?.toLowerCase().includes("identity changed")
    )
      setMountIssue(true);
  }, [latest?.error, latest?.issue_code]);
  const filter = {
    source_id: sourceId,
    name,
    suffix,
    path: prefix,
    sidecar_state: prior,
    metadata_state: metadata,
    ...(minSize !== ""
      ? { min_bytes: Math.round(Number(minSize) * 1024 ** 2) }
      : {}),
    ...(maxSize !== ""
      ? { max_bytes: Math.round(Number(maxSize) * 1024 ** 2) }
      : {}),
    ...(after
      ? { modified_after: Date.parse(`${after}T00:00:00Z`) / 1000 }
      : {}),
    ...(before
      ? { modified_before: Date.parse(`${before}T23:59:59Z`) / 1000 }
      : {}),
  };
  const raw = JSON.stringify(filter);
  const deferred = useDeferredValue(raw);
  const params = new URLSearchParams(
    Object.entries(JSON.parse(deferred)).map(([k, v]) => [k, String(v)]),
  ).toString();
  useEffect(() => {
    setCursor(0);
    setPrevious([]);
  }, [deferred]);
  const entries = useQuery({
    queryKey: ["discovery", "entries", deferred, cursor],
    queryFn: ({ signal }) =>
      apiJson<{ items: Entry[]; next_cursor: number | null }>(
        `/api/volume/entries?${params}&cursor=${cursor}&limit=100`,
        { signal },
      ),
    enabled: showEntries && sourceId !== "" && deferred === raw,
    refetchInterval:
      showEntries && latest && ["queued", "running"].includes(latest.status)
        ? 5000
        : false,
  });
  const summary = useQuery({
    queryKey: ["discovery", "summary", deferred],
    queryFn: ({ signal }) =>
      apiJson<{ files: number; bytes: number; unknown_sizes: number }>(
        `/api/volume/summary?${params}`,
        { signal },
      ),
    enabled: matching && sourceId !== "" && deferred === raw,
  });
  const frozen = useQuery({
    queryKey: ["discovery", "frozen", selectedId, frozenCursor],
    queryFn: () =>
      apiJson<{ items: Entry[]; next_cursor: number | null }>(
        `/api/volume/selections/${selectedId}/entries?cursor=${frozenCursor}&limit=100`,
      ),
    enabled: review && selectedId !== null,
  });
  const membership = useQuery({
    queryKey: ["discovery", "membership", selectedId],
    queryFn: async ({ signal }) => {
      const members: Entry[] = [];
      let after = 0;
      do {
        const page = await apiJson<{
          items: Entry[];
          next_cursor: number | null;
        }>(
          `/api/volume/selections/${selectedId}/entries?cursor=${after}&limit=500`,
          { signal },
        );
        members.push(...page.items);
        if (members.length > 10000)
          throw new Error(
            "This selection exceeds the Intake limit. Choose a smaller selection.",
          );
        if (page.next_cursor === null) break;
        after = page.next_cursor;
      } while (!signal.aborted);
      return members;
    },
    enabled: showEntries && selectedId !== null,
    staleTime: Infinity,
  });
  const selections = useQuery({
    queryKey: ["discovery", "saved"],
    queryFn: () =>
      apiJson<{ items: Selection[] }>("/api/volume/selections?limit=100"),
    enabled: saved,
  });
  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await client.invalidateQueries({ queryKey: ["discovery"] });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      if (message.toLowerCase().includes("identity changed"))
        setMountIssue(true);
    } finally {
      setBusy(false);
    }
  };
  const hasSelection =
    directFiles.length > 0 || selectedId !== null || draft.size > 0;
  const clear = () => {
    onSelect(null);
    onFiles([]);
    setDraft(new Map());
    setReview(false);
  };
  const mayClear = () =>
    !hasSelection || window.confirm("Clear the current file selection?");
  const switchSource = (id: number) => {
    if (id === sourceId || !mayClear()) return;
    clear();
    setSourceId(id);
    setShowEntries(false);
    setMountIssue(false);
    setPartial(false);
    setError(null);
    setCursor(0);
    setPrevious([]);
    const found = sources.data?.items.find((item) => item.id === id);
    if (found) localStorage.setItem("osii:last-discovery-root", found.root);
  };
  const register = () =>
    act(async () => {
      const path = normalize(root.trim());
      const overlap = sources.data?.items.find((item) => {
        const other = normalize(item.root);
        return (
          path === other ||
          path.startsWith(`${other}/`) ||
          other.startsWith(`${path}/`)
        );
      });
      if (!mayClear()) return;
      if (overlap) {
        clear();
        setSourceId(overlap.id);
        setAdding(false);
        setShowEntries(false);
        localStorage.setItem("osii:last-discovery-root", overlap.root);
        setLocationNotice(
          `Using the existing location ${overlap.root}. Browse inside it to select files.`,
        );
        return;
      }
      const value = await apiJson<Source>("/api/volume/sources", {
        method: "POST",
        json: { root: root.trim() },
      });
      clear();
      setSourceId(value.id);
      localStorage.setItem("osii:last-discovery-root", value.root);
      setAdding(false);
      setShowEntries(false);
      setMountIssue(false);
      setPartial(false);
    });
  const choose = (value: Selection) => {
    if (!JSON.parse(value.request).filters?.source_id || value.count > 10000) {
      setError(
        "Choose files from one location, up to 10,000 files per selection.",
      );
      return;
    }
    client.setQueryData(["discovery", "selection", value.id], value);
    onFiles([]);
    onSelect(value.count ? value.id : null);
    setDraft(new Map());
    setMatching(false);
    setSaved(false);
    setReview(false);
    localStorage.setItem("osii:last-intake-selection", String(value.id));
  };
  const incomplete = Boolean(latest && latest.status !== "done");
  const scanOptionsValid =
    Number.isInteger(readers) &&
    readers >= 1 &&
    readers <= 8 &&
    (depth === "" ||
      (Number.isInteger(Number(depth)) &&
        Number(depth) >= 0 &&
        Number(depth) <= 256));
  const validBudgets =
    Number.isInteger(maxFiles) &&
    maxFiles >= 1 &&
    maxFiles <= 10000 &&
    Number.isFinite(budget) &&
    budget >= 1;
  const freeze = (explicit: boolean) =>
    act(async () => {
      const value = await apiJson<Selection>("/api/volume/selections", {
        method: "POST",
        json: {
          filters: explicit
            ? { source_id: sourceId }
            : {
                ...filter,
                metadata_state: "known",
                max_bytes: Math.min(
                  filter.max_bytes ?? 50 * 1024 ** 2,
                  50 * 1024 ** 2,
                ),
              },
          ...(explicit ? { entry_ids: [...draft.keys()] } : {}),
          max_files: explicit ? Math.max(100, draft.size) : maxFiles,
          max_bytes: budget * 1024 ** 2,
          allow_partial: partial,
        },
      });
      if (!value.count)
        throw new Error(
          "No eligible files matched. Review the filters and limits.",
        );
      choose(value);
    });
  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length || !mayClear()) return;
    if (
      files.length > 10000 ||
      files.some((file) => file.size > 50 * 1024 ** 2) ||
      files.reduce((sum, file) => sum + file.size, 0) > 1024 ** 3
    ) {
      setError("Choose up to 10,000 files, 50 MiB per file, and 1 GiB total.");
      return;
    }
    await act(async () => {
      const result = await uploadQueueFiles(files);
      clear();
      onFiles(
        result.uploads.map((item) => ({
          path: item.path,
          name: item.name,
          size_bytes: item.size_bytes,
        })),
      );
    });
  };
  const count = selectedId
    ? (selected.data?.count ?? 0)
    : directFiles.length || draft.size;
  const total = selectedId
    ? (selected.data?.bytes ?? 0)
    : (directFiles.length ? directFiles : [...draft.values()]).reduce(
        (sum, file) => sum + (file.size_bytes ?? 0),
        0,
      );
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
      <Stack spacing={2}>
        <Typography variant="h6" component="h2" fontWeight={750}>
          1. Choose location
        </Typography>
        {error && (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        {locationNotice && (
          <Alert severity="info" onClose={() => setLocationNotice(null)}>
            {locationNotice}
          </Alert>
        )}
        {sources.isError && (
          <Alert
            severity="error"
            action={
              <Button onClick={() => void sources.refetch()}>Retry</Button>
            }
          >
            Locations unavailable.
          </Alert>
        )}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            select
            fullWidth
            size="small"
            label="Location"
            disabled={busy}
            value={source ? sourceId : ""}
            onChange={(e) => switchSource(Number(e.target.value))}
          >
            {(sources.data?.items ?? []).map((item) => (
              <MenuItem key={item.id} value={item.id}>
                {item.root}
              </MenuItem>
            ))}
          </TextField>
          <Button
            startIcon={<FolderOutlinedIcon />}
            disabled={busy}
            sx={{ flexShrink: 0 }}
            onClick={() => {
              setRoot("");
              setAdding(true);
            }}
          >
            Add location
          </Button>
          <Button
            component="label"
            startIcon={<UploadFileOutlinedIcon />}
            disabled={busy}
            sx={{ flexShrink: 0 }}
          >
            Upload files
            <input hidden type="file" multiple onChange={upload} />
          </Button>
        </Stack>
        <Divider />
        <Typography variant="h6" component="h2" fontWeight={750}>
          2. Select files
        </Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button
            variant="contained"
            startIcon={<FolderOutlinedIcon />}
            disabled={!source || busy}
            onClick={() => {
              const replace =
                Boolean(selectedId) ||
                directFiles.some(
                  (file) =>
                    !normalize(file.path).startsWith(
                      `${normalize(source?.root ?? "")}/`,
                    ),
                );
              if (!replace || mayClear()) {
                if (replace) clear();
                setFileBrowser(true);
              }
            }}
          >
            Browse files
          </Button>
          <Button
            variant="outlined"
            disabled={
              !source ||
              busy ||
              Boolean(
                latest &&
                ["queued", "running", "paused"].includes(latest.status),
              )
            }
            onClick={() =>
              void act(async () => {
                await apiJson(`/api/volume/sources/${sourceId}/scan`, {
                  method: "POST",
                  json: {
                    include_patterns: lines(include),
                    exclude_patterns: lines(exclude),
                    max_depth: depth === "" ? null : Number(depth),
                    readers,
                    show_hidden: hidden,
                    cross_filesystems: cross,
                  },
                });
              })
            }
          >
            Start background scan
          </Button>
          <Button
            disabled={!latest}
            onClick={() => setShowEntries((value) => !value)}
          >
            {showEntries ? "Hide discovered files" : "View discovered files"}
          </Button>
          <Button onClick={() => setSaved(true)}>Saved selections</Button>
        </Stack>
        <details>
          <summary>Scan options</summary>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                fullWidth
                size="small"
                multiline
                label="Include patterns"
                value={include}
                onChange={(e) => setInclude(e.target.value)}
              />
              <TextField
                fullWidth
                size="small"
                multiline
                label="Exclude patterns"
                value={exclude}
                onChange={(e) => setExclude(e.target.value)}
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                size="small"
                type="number"
                label="Maximum depth"
                placeholder="Unlimited"
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
                inputProps={{ min: 0, max: 256 }}
              />
              <TextField
                size="small"
                type="number"
                label="Readers"
                value={readers}
                onChange={(e) => setReaders(Number(e.target.value))}
                inputProps={{ min: 1, max: 8 }}
              />
            </Stack>
            <Stack direction="row">
              <FormControlLabel
                control={
                  <Checkbox
                    checked={hidden}
                    onChange={(e) => setHidden(e.target.checked)}
                  />
                }
                label="Include hidden paths"
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={cross}
                    onChange={(e) => setCross(e.target.checked)}
                  />
                }
                label="Cross filesystem boundaries"
              />
            </Stack>
          </Stack>
        </details>
        {latest && <ScanCard key={latest.id} run={latest} compact />}
        {runs.isError && (
          <Alert
            severity="error"
            action={<Button onClick={() => void runs.refetch()}>Retry</Button>}
          >
            Scan status unavailable.
          </Alert>
        )}
        {mountIssue && (
          <Alert severity="warning">
            <Stack spacing={1}>
              <Typography>
                This location appears different from the folder previously
                scanned.
              </Typography>
              <Typography variant="body2">
                Check that the original dataset is mounted here. Cancel active
                scans and wait for them to stop. Confirming keeps history,
                clears old selections, and requires a new scan.
              </Typography>
              <TextField
                size="small"
                label="Confirm the registered path"
                value={confirmRoot}
                onChange={(e) => setConfirmRoot(e.target.value)}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={verified}
                    onChange={(e) => setVerified(e.target.checked)}
                  />
                }
                label="I checked that this is the original dataset"
              />
              <Button
                disabled={busy || !verified || confirmRoot !== source?.root}
                onClick={() =>
                  void act(async () => {
                    await apiJson(`/api/volume/sources/${sourceId}/rebind`, {
                      method: "POST",
                      json: { root: confirmRoot },
                    });
                    clear();
                    setMountIssue(false);
                    setVerified(false);
                  })
                }
              >
                Confirm location and rescan next
              </Button>
            </Stack>
          </Alert>
        )}
        {showEntries && (
          <Stack spacing={1.5}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                fullWidth
                size="small"
                label="Filename"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <TextField
                size="small"
                label="Extension"
                value={suffix}
                onChange={(e) => setSuffix(e.target.value)}
              />
              <Button
                disabled={busy || deferred !== raw}
                onClick={() => setMatching(true)}
              >
                Select matching files…
              </Button>
            </Stack>
            <details>
              <summary>More filters</summary>
              <Stack spacing={1} sx={{ pt: 1 }}>
                <TextField
                  size="small"
                  label="Path prefix"
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                />
                <Stack direction="row" spacing={1}>
                  <TextField
                    select
                    fullWidth
                    size="small"
                    label="Previously processed"
                    value={prior}
                    onChange={(e) => setPrior(e.target.value)}
                  >
                    {[
                      ["any", "Any"],
                      ["missing", "Not processed"],
                      ["processed", "Processed"],
                    ].map(([value, label]) => (
                      <MenuItem key={value} value={value}>
                        {label}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    select
                    fullWidth
                    size="small"
                    label="Metadata"
                    value={metadata}
                    onChange={(e) => setMetadata(e.target.value)}
                  >
                    {[
                      ["any", "Any"],
                      ["known", "Available"],
                      ["unavailable", "Unavailable"],
                    ].map(([value, label]) => (
                      <MenuItem key={value} value={value}>
                        {label}
                      </MenuItem>
                    ))}
                  </TextField>
                </Stack>
                <Stack direction="row" spacing={1}>
                  <TextField
                    size="small"
                    type="number"
                    label="Minimum MiB"
                    value={minSize}
                    onChange={(e) => setMinSize(e.target.value)}
                  />
                  <TextField
                    size="small"
                    type="number"
                    label="Maximum MiB"
                    value={maxSize}
                    onChange={(e) => setMaxSize(e.target.value)}
                  />
                </Stack>
                <Stack direction="row" spacing={1}>
                  <TextField
                    size="small"
                    type="date"
                    label="Modified after"
                    InputLabelProps={{ shrink: true }}
                    value={after}
                    onChange={(e) => setAfter(e.target.value)}
                  />
                  <TextField
                    size="small"
                    type="date"
                    label="Modified before"
                    InputLabelProps={{ shrink: true }}
                    value={before}
                    onChange={(e) => setBefore(e.target.value)}
                  />
                </Stack>
              </Stack>
            </details>
            {(entries.isFetching ||
              (selectedId !== null && membership.isFetching)) && (
              <LinearProgress />
            )}
            {membership.isError && (
              <Alert severity="error">
                Could not load selected checkboxes. Review or clear the
                selection to continue.
              </Alert>
            )}
            {entries.isError && (
              <Alert
                severity="error"
                action={
                  <Button onClick={() => void entries.refetch()}>Retry</Button>
                }
              >
                {String(entries.error)}
              </Alert>
            )}
            <List
              dense
              aria-label="Discovered files"
              sx={{ maxHeight: 360, overflow: "auto" }}
            >
              {entries.data?.items.map((entry) => {
                const old = entry.scan_run_id !== latest?.id;
                const disabled =
                  old ||
                  entry.metadata_state !== "known" ||
                  entry.size_bytes === null ||
                  entry.size_bytes > 50 * 1024 ** 2;
                return (
                  <ListItem key={entry.id} disablePadding>
                    <ListItemButton
                      disabled={
                        disabled ||
                        busy ||
                        (selectedId !== null && !membership.data)
                      }
                      onClick={() => {
                        onSelect(null);
                        onFiles([]);
                        setDraft((current) => {
                          const next = new Map(
                            selectedId
                              ? membership.data?.map(
                                  (item) => [item.id, item] as const,
                                )
                              : current,
                          );
                          if (next.has(entry.id)) next.delete(entry.id);
                          else next.set(entry.id, entry);
                          return next;
                        });
                      }}
                    >
                      <Checkbox
                        checked={
                          selectedId
                            ? Boolean(
                                membership.data?.some(
                                  (item) => item.id === entry.id,
                                ),
                              )
                            : draft.has(entry.id)
                        }
                        tabIndex={-1}
                      />
                      <ListItemText
                        primary={entry.path}
                        secondary={
                          old
                            ? "Earlier scan — rediscover before selecting"
                            : (entry.metadata_error ??
                              (entry.size_bytes === null
                                ? "Size unavailable"
                                : `${bytes(entry.size_bytes)}${entry.size_bytes > 50 * 1024 ** 2 ? " · exceeds 50 MiB processing limit" : ""}`))
                        }
                      />
                    </ListItemButton>
                  </ListItem>
                );
              })}
            </List>
            {entries.data && !entries.data.items.length && (
              <Typography color="text.secondary">
                No discovered files match.
              </Typography>
            )}
            <Stack direction="row" spacing={1}>
              <Button
                disabled={!previous.length}
                onClick={() => {
                  setCursor(previous[previous.length - 1]);
                  setPrevious((items) => items.slice(0, -1));
                }}
              >
                Previous page
              </Button>
              <Button
                disabled={!entries.data?.next_cursor}
                onClick={() => {
                  setPrevious((items) => [...items, cursor]);
                  setCursor(entries.data!.next_cursor!);
                }}
              >
                Next page
              </Button>
            </Stack>
            {incomplete && (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={partial}
                    onChange={(e) => setPartial(e.target.checked)}
                  />
                }
                label="Use files found so far; the scan is incomplete"
              />
            )}
            {draft.size > 0 && (
              <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                flexWrap="wrap"
                useFlexGap
              >
                <Typography variant="body2">
                  Selected: {draft.size} ·{" "}
                  {bytes(
                    [...draft.values()].reduce(
                      (sum, item) => sum + (item.size_bytes ?? 0),
                      0,
                    ),
                  )}
                </Typography>
                <Button
                  variant="contained"
                  disabled={
                    busy || (incomplete && !partial) || draft.size > 10000
                  }
                  onClick={() => void freeze(true)}
                >
                  Use {draft.size} {draft.size === 1 ? "file" : "files"}
                </Button>
              </Stack>
            )}
          </Stack>
        )}
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          flexWrap="wrap"
          useFlexGap
        >
          <Typography fontWeight={700}>
            Selected files: {count}
            {count ? ` · ${bytes(total)}` : ""}
          </Typography>
          {count > 0 && (
            <>
              <Button
                onClick={() => {
                  setFrozenCursor(0);
                  setReview((value) => !value);
                }}
              >
                {review ? "Hide selection" : "Review selection"}
              </Button>
              <Button onClick={clear}>Clear</Button>
            </>
          )}
        </Stack>
        {selected.isError && (
          <Alert severity="error">
            Saved selection unavailable. Select files again.
          </Alert>
        )}
        {review && (
          <Stack spacing={1}>
            {(directFiles.length ? directFiles : [...draft.values()]).map(
              (file) => (
                <Typography
                  key={file.path}
                  variant="body2"
                  sx={{ overflowWrap: "anywhere" }}
                >
                  {file.path}
                </Typography>
              ),
            )}
            {frozen.data?.items.map((entry) => (
              <Typography
                key={entry.id}
                variant="body2"
                sx={{ overflowWrap: "anywhere" }}
              >
                {entry.path}
              </Typography>
            ))}
            {frozen.isError && (
              <Alert severity="error">Could not load selection.</Alert>
            )}
            {frozen.data?.next_cursor && (
              <Button
                onClick={() => setFrozenCursor(frozen.data!.next_cursor!)}
              >
                Next selected files
              </Button>
            )}
            {frozenCursor > 0 && (
              <Button onClick={() => setFrozenCursor(0)}>
                First selected files
              </Button>
            )}
          </Stack>
        )}
        <Dialog
          open={adding}
          onClose={() => setAdding(false)}
          fullWidth
          maxWidth="sm"
        >
          <DialogTitle>Add location</DialogTitle>
          <DialogContent>
            <Stack direction="row" spacing={1} sx={{ pt: 1 }}>
              <TextField
                fullWidth
                size="small"
                label="Folder path"
                placeholder="Paste a folder or share path"
                value={root}
                onChange={(e) => setRoot(e.target.value)}
              />
              <Button onClick={() => setFolderBrowser(true)}>Browse…</Button>
            </Stack>
            {error && (
              <Alert severity="error" sx={{ mt: 1 }}>
                {error}
              </Alert>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setAdding(false)}>Cancel</Button>
            <Button
              variant="contained"
              disabled={busy || !root.trim()}
              onClick={() => void register()}
            >
              Add location
            </Button>
          </DialogActions>
        </Dialog>
        <LocationBrowser
          open={folderBrowser}
          foldersOnly
          initialPath={root || undefined}
          onClose={() => setFolderBrowser(false)}
          onFolder={(path) => {
            setRoot(path);
            setFolderBrowser(false);
          }}
        />
        <LocationBrowser
          open={fileBrowser}
          initialPath={source?.root}
          boundaryPath={source?.root}
          selected={directFiles}
          onClose={() => setFileBrowser(false)}
          onFiles={(files) => {
            onSelect(null);
            setDraft(new Map());
            onFiles(files);
            setFileBrowser(false);
            setReview(false);
          }}
        />
        <Dialog
          open={matching}
          onClose={() => setMatching(false)}
          fullWidth
          maxWidth="sm"
        >
          <DialogTitle>Select matching files</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1 }}>
              <Typography>
                {summary.data
                  ? `${summary.data.files.toLocaleString()} matching files · ${bytes(summary.data.bytes)}`
                  : "Checking matches…"}
              </Typography>
              {summary.isError && (
                <Alert severity="error">
                  Could not check matches. Close and retry.
                </Alert>
              )}
              <Stack direction="row" spacing={1}>
                <TextField
                  type="number"
                  size="small"
                  label="File limit"
                  value={maxFiles}
                  onChange={(e) => setMaxFiles(Number(e.target.value))}
                  inputProps={{ min: 1, max: 10000 }}
                />
                <TextField
                  type="number"
                  size="small"
                  label="Total MiB limit"
                  value={budget}
                  onChange={(e) => setBudget(Number(e.target.value))}
                  inputProps={{ min: 1 }}
                />
              </Stack>
              <Typography variant="body2">
                Select up to {maxFiles} files within {budget} MiB. Later
                discoveries stay unselected.
              </Typography>
              {incomplete && (
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={partial}
                      onChange={(e) => setPartial(e.target.checked)}
                    />
                  }
                  label="Use files found so far; the scan is incomplete"
                />
              )}
              {hasSelection && (
                <Typography variant="caption">
                  This replaces your current selection.
                </Typography>
              )}
              {error && <Alert severity="error">{error}</Alert>}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setMatching(false)}>Cancel</Button>
            <Button
              variant="contained"
              disabled={
                busy ||
                !validBudgets ||
                !summary.data?.files ||
                summary.isFetching ||
                summary.isError ||
                (incomplete && !partial)
              }
              onClick={() => void freeze(false)}
            >
              Select files
            </Button>
          </DialogActions>
        </Dialog>
        <Dialog open={saved} onClose={() => setSaved(false)} fullWidth>
          <DialogTitle>Saved selections</DialogTitle>
          <DialogContent>
            <List>
              {selections.data?.items.map((value) => (
                <ListItemButton
                  key={value.id}
                  onClick={() => {
                    if (mayClear()) {
                      clear();
                      choose(value);
                    }
                  }}
                >
                  <ListItemText
                    primary={`${value.count} files · ${bytes(value.bytes)}`}
                    secondary={new Date(value.created * 1000).toLocaleString()}
                  />
                </ListItemButton>
              ))}
            </List>
            {selections.isError && (
              <Alert severity="error">Could not load saved selections.</Alert>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setSaved(false)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Stack>
    </Paper>
  );
}
