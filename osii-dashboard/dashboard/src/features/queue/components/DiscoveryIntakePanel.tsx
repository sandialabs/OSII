import { useDeferredValue, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { apiJson } from "../../../api/client";

type Source = { id: number; root: string; name: string };
type Scan = {
  id: number;
  status: string;
  observed_entries: number;
  known_bytes: number;
  metadata_errors: number;
  completed: number;
  failed: number;
  updated: number;
  created: number;
  error: string | null;
  directories?: Record<string, number>;
  current_paths?: string[];
};
type Entry = {
  id: number;
  path: string;
  size_bytes: number | null;
  metadata_error: string | null;
  observed: number;
};
type Selection = {
  id: number;
  count: number;
  bytes: number;
  coverage: string;
  request: string;
};
const bytes = (value: number) => `${(value / 1024 / 1024).toFixed(1)} MiB`;
const lines = (value: string) =>
  value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

export function DiscoveryIntakePanel({
  selectedId,
  onSelect,
}: {
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}) {
  const client = useQueryClient();
  const [sourceId, setSourceId] = useState<number | "">("");
  const [root, setRoot] = useState("");
  const [include, setInclude] = useState("");
  const [exclude, setExclude] = useState("");
  const [hidden, setHidden] = useState(false);
  const [crossFilesystems, setCrossFilesystems] = useState(false);
  const [depth, setDepth] = useState("");
  const [readers, setReaders] = useState(2);
  const [name, setName] = useState("");
  const [prefix, setPrefix] = useState("");
  const [suffix, setSuffix] = useState("");
  const [prior, setPrior] = useState("any");
  const [metadata, setMetadata] = useState("any");
  const [minSize, setMinSize] = useState("");
  const [maxSize, setMaxSize] = useState("");
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [maxFiles, setMaxFiles] = useState(100);
  const [budget, setBudget] = useState(1024);
  const [partial, setPartial] = useState(false);
  const [sample, setSample] = useState(false);
  const [seed, setSeed] = useState("osii");
  const [cursor, setCursor] = useState(0);
  const [frozenCursor, setFrozenCursor] = useState(0);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [restoreId, setRestoreId] = useState("");
  const [verifiedMount, setVerifiedMount] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const restored = useQuery({
    queryKey: ["discovery", "restore", selectedId],
    queryFn: () => apiJson<Selection>(`/api/volume/selections/${selectedId}`),
    enabled: selectedId !== null,
  });
  useEffect(() => {
    if (restored.data) {
      setSelection(restored.data);
      const id = JSON.parse(restored.data.request).filters?.source_id;
      if (id) setSourceId(id);
    }
  }, [restored.data]);
  const sources = useQuery({
    queryKey: ["discovery", "sources"],
    queryFn: () => apiJson<{ items: Source[] }>("/api/volume/sources"),
  });
  useEffect(() => {
    if (sourceId === "" && sources.data?.items.length)
      setSourceId(sources.data.items[0].id);
  }, [sources.data, sourceId]);
  const scans = useQuery({
    queryKey: ["discovery", "scans", sourceId],
    queryFn: () =>
      apiJson<{ items: Scan[] }>(`/api/volume/sources/${sourceId}/scans`),
    enabled: sourceId !== "",
    refetchInterval: 2000,
  });
  const latest = scans.data?.items[0];
  const run = useQuery({
    queryKey: ["discovery", "scan", latest?.id],
    queryFn: () => apiJson<Scan>(`/api/volume/runs/${latest?.id}`),
    enabled: Boolean(latest),
    refetchInterval: 2000,
  });
  const events = useQuery({
    queryKey: ["discovery", "events", latest?.id],
    queryFn: () =>
      apiJson<{
        items: { id: number; path: string | null; message: string }[];
      }>(`/api/volume/runs/${latest?.id}/events?limit=20`),
    enabled: Boolean(latest),
    refetchInterval: 5000,
  });
  const rawFilter = JSON.stringify({
    source_id: sourceId,
    name,
    path: prefix,
    suffix,
    sidecar_state: prior,
    metadata_state: metadata,
    ...(minSize !== ""
      ? { min_bytes: Math.round(Number(minSize) * 1024 * 1024) }
      : {}),
    ...(maxSize !== ""
      ? { max_bytes: Math.round(Number(maxSize) * 1024 * 1024) }
      : {}),
    ...(after
      ? { modified_after: Date.parse(`${after}T00:00:00Z`) / 1000 }
      : {}),
    ...(before
      ? { modified_before: Date.parse(`${before}T23:59:59Z`) / 1000 }
      : {}),
  });
  const filter = useDeferredValue(rawFilter);
  const filtersReady = sourceId !== "" && filter === rawFilter;
  const params = new URLSearchParams(
    Object.entries(JSON.parse(filter)).map(([k, v]) => [k, String(v)]),
  ).toString();
  useEffect(() => {
    setCursor(0);
  }, [filter]);
  const entries = useQuery({
    queryKey: ["discovery", "entries", filter, cursor],
    queryFn: () =>
      apiJson<{ items: Entry[]; next_cursor: number | null }>(
        `/api/volume/entries?${params}&cursor=${cursor}&limit=100`,
      ),
    enabled: filtersReady,
    refetchInterval: 5000,
  });
  const summary = useQuery({
    queryKey: ["discovery", "summary", filter],
    queryFn: () =>
      apiJson<{ files: number; bytes: number; unknown_sizes: number }>(
        `/api/volume/summary?${params}`,
      ),
    enabled: filtersReady,
    refetchInterval: 5000,
  });
  const frozen = useQuery({
    queryKey: ["discovery", "frozen", selection?.id, frozenCursor],
    queryFn: () =>
      apiJson<{ items: Entry[]; next_cursor: number | null }>(
        `/api/volume/selections/${selection?.id}/entries?cursor=${frozenCursor}&limit=100`,
      ),
    enabled: Boolean(selection),
  });
  const act = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await client.invalidateQueries({ queryKey: ["discovery"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const choose = (value: Selection) => {
    const id = JSON.parse(value.request).filters?.source_id;
    if (id) setSourceId(id);
    setSelection(value);
    setFrozenCursor(0);
    onSelect(value.count ? value.id : null);
  };
  const control = (id: number, action: string) =>
    act(async () => {
      await apiJson(`/api/volume/runs/${id}/${action}`, {
        method: "POST",
        json: {},
      });
    });
  const validBudgets =
    Number.isInteger(maxFiles) &&
    maxFiles >= 1 &&
    maxFiles <= 10000 &&
    Number.isFinite(budget) &&
    budget >= 1;
  const active = latest?.status === "queued" || latest?.status === "running";
  const status = run.data ?? latest;
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Typography variant="h6">Discover a shared drive</Typography>
        <Typography variant="body2">
          Scan names and metadata into a local inventory. Discovery reads no
          document contents and invokes no models. Close this page safely;
          checkpoints and frozen selections survive restart.
        </Typography>
        {error && <Alert severity="error">{error}</Alert>}
        {sources.isError && (
          <Alert severity="error">{String(sources.error)}</Alert>
        )}
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          useFlexGap
          sx={{
            flexWrap: "wrap",
            "& > .MuiTextField-root": {
              flex: { sm: "1 1 170px" },
              minWidth: { sm: 170 },
            },
          }}
        >
          <TextField
            select
            fullWidth
            size="small"
            label="Registered source"
            value={sourceId}
            onChange={(e) => {
              setSourceId(Number(e.target.value));
              setSelection(null);
              onSelect(null);
              setCursor(0);
            }}
          >
            {(sources.data?.items ?? []).map((source) => (
              <MenuItem key={source.id} value={source.id}>
                {source.name} — {source.root}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            fullWidth
            size="small"
            label="New share or folder path"
            value={root}
            onChange={(e) => setRoot(e.target.value)}
          />
          <Button
            disabled={busy || !root.trim()}
            onClick={() =>
              void act(async () => {
                const value = await apiJson<Source>("/api/volume/sources", {
                  method: "POST",
                  json: { root: root.trim() },
                });
                setSourceId(value.id);
                setSelection(null);
                onSelect(null);
              })
            }
          >
            Register source
          </Button>
        </Stack>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          useFlexGap
          sx={{
            flexWrap: "wrap",
            "& > .MuiTextField-root": {
              flex: { sm: "1 1 170px" },
              minWidth: { sm: 170 },
            },
          }}
        >
          <TextField
            fullWidth
            multiline
            size="small"
            label="Scan include patterns (one per line)"
            helperText="Blank includes all files; directories are still traversed."
            value={include}
            onChange={(e) => setInclude(e.target.value)}
          />
          <TextField
            fullWidth
            multiline
            size="small"
            label="Scan exclude patterns (one per line)"
            helperText="Excluded directories are not traversed. Rules are frozen per scan."
            value={exclude}
            onChange={(e) => setExclude(e.target.value)}
          />
          <TextField
            size="small"
            type="number"
            label="Maximum depth"
            value={depth}
            onChange={(e) => setDepth(e.target.value)}
            helperText="Blank: unlimited; 0: root only"
            inputProps={{ min: 0, max: 256 }}
          />
          <TextField
            size="small"
            type="number"
            label="Metadata readers"
            value={readers}
            onChange={(e) => setReaders(Number(e.target.value))}
            helperText="Default 2; maximum 8"
            inputProps={{ min: 1, max: 8 }}
          />
        </Stack>
        <Stack direction="row" flexWrap="wrap" spacing={1}>
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
                checked={crossFilesystems}
                onChange={(e) => setCrossFilesystems(e.target.checked)}
              />
            }
            label="Cross filesystem boundaries"
          />
          <Button
            variant="contained"
            disabled={
              busy ||
              sourceId === "" ||
              active ||
              readers < 1 ||
              readers > 8 ||
              (depth !== "" && (Number(depth) < 0 || Number(depth) > 256))
            }
            onClick={() =>
              void act(async () => {
                await apiJson(`/api/volume/sources/${sourceId}/scan`, {
                  method: "POST",
                  json: {
                    include_patterns: lines(include),
                    exclude_patterns: lines(exclude),
                    show_hidden: hidden,
                    max_depth: depth === "" ? null : Number(depth),
                    readers,
                    cross_filesystems: crossFilesystems,
                  },
                });
              })
            }
          >
            Start discovery
          </Button>
        </Stack>
        {status && (
          <Stack spacing={1}>
            <Typography fontWeight={700}>
              Scan #{status.id}: {status.status}
            </Typography>
            {active && <LinearProgress />}
            <Typography variant="body2">
              {status.observed_entries.toLocaleString()} observed entries ·{" "}
              {bytes(status.known_bytes)} known logical bytes ·{" "}
              {status.completed} directory attempts completed ·{" "}
              {status.metadata_errors} metadata failures
            </Typography>
            <Typography variant="caption">
              Elapsed wall time since queued:{" "}
              {Math.max(
                0,
                Math.floor(
                  (["done", "error", "cancelled"].includes(status.status)
                    ? status.updated
                    : Date.now() / 1000) - status.created,
                ),
              )}{" "}
              seconds (includes pauses).
            </Typography>
            <Typography variant="caption">
              Directory tasks:{" "}
              {Object.entries(status.directories ?? {})
                .map(([state, count]) => `${count} ${state}`)
                .join(" · ")}{" "}
              · Last activity {new Date(status.updated * 1000).toLocaleString()}
            </Typography>
            {status.current_paths?.map((p) => (
              <Typography key={p} variant="caption">
                Reading: {p || "(source root)"}
              </Typography>
            ))}
            {status.error && <Alert severity="warning">{status.error}</Alert>}
            <Alert severity={status.status === "done" ? "success" : "warning"}>
              {status.status === "done"
                ? "Discovery completed under its saved traversal rules. This is a metadata observation, not a content-read permission guarantee."
                : "Coverage is incomplete. Unvisited and denied paths may be absent. Resume after reconnecting or fixing access; a partial batch requires acknowledgement below."}
            </Alert>
            <Stack direction="row" spacing={1}>
              {active && (
                <Button
                  disabled={busy}
                  onClick={() => void control(status.id, "pause")}
                >
                  Pause scan
                </Button>
              )}
              {["paused", "error"].includes(status.status) && (
                <Button
                  disabled={busy}
                  onClick={() => void control(status.id, "resume")}
                >
                  Resume scan / retry failures
                </Button>
              )}
              {["running", "queued", "paused"].includes(status.status) && (
                <Button
                  disabled={busy}
                  onClick={() => void control(status.id, "cancel")}
                >
                  Cancel scan
                </Button>
              )}
            </Stack>
            {(events.data?.items ?? []).length > 0 && (
              <details>
                <summary>Discovery issues (first 20)</summary>
                {events.data?.items.map((event) => (
                  <Typography key={event.id} variant="body2">
                    {event.path || "Source"}: {event.message}
                  </Typography>
                ))}
              </details>
            )}
          </Stack>
        )}
        <details>
          <summary>Changed mount identity</summary>
          <Stack spacing={1}>
            <Typography variant="body2">
              After a remount, verify that this is the original dataset. Cancel
              active scans first. Rebinding invalidates old selections and
              requires fresh discovery; it preserves historical evidence.
            </Typography>
            <FormControlLabel
              control={
                <Checkbox
                  checked={verifiedMount}
                  onChange={(e) => setVerifiedMount(e.target.checked)}
                />
              }
              label="I verified the mounted dataset and entered its exact registered path above"
            />
            <Button
              disabled={
                busy || !verifiedMount || sourceId === "" || !root.trim()
              }
              onClick={() =>
                void act(async () => {
                  await apiJson(`/api/volume/sources/${sourceId}/rebind`, {
                    method: "POST",
                    json: { root: root.trim() },
                  });
                  setSelection(null);
                  onSelect(null);
                  setVerifiedMount(false);
                })
              }
            >
              Rebind verified source identity
            </Button>
          </Stack>
        </details>
        <Typography fontWeight={700}>
          Filter inventory and freeze a bounded batch
        </Typography>
        <Typography variant="body2">
          Filters query local SQLite without rereading the share. New selections
          use files observed in the latest scan; unknown sizes are never
          eligible.
        </Typography>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          useFlexGap
          sx={{
            flexWrap: "wrap",
            "& > .MuiTextField-root": {
              flex: { sm: "1 1 170px" },
              minWidth: { sm: 170 },
            },
          }}
        >
          <TextField
            fullWidth
            size="small"
            label="Filename contains"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <TextField
            fullWidth
            size="small"
            label="Folder prefix"
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
          />
          <TextField
            size="small"
            label="Extension"
            value={suffix}
            onChange={(e) => setSuffix(e.target.value)}
          />
          <TextField
            select
            size="small"
            label="Prior Intake"
            value={prior}
            onChange={(e) => setPrior(e.target.value)}
          >
            {[
              ["any", "Any"],
              ["missing", "Not processed at this revision"],
              ["processed", "Processed at this revision"],
            ].map(([v, l]) => (
              <MenuItem key={v} value={v}>
                {l}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label="Metadata"
            value={metadata}
            onChange={(e) => setMetadata(e.target.value)}
          >
            {[
              ["any", "Any"],
              ["known", "Known attributes"],
              ["unavailable", "Unavailable attributes"],
            ].map(([v, l]) => (
              <MenuItem key={v} value={v}>
                {l}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          useFlexGap
          sx={{
            flexWrap: "wrap",
            "& > .MuiTextField-root": {
              flex: { sm: "1 1 170px" },
              minWidth: { sm: 170 },
            },
          }}
        >
          <TextField
            size="small"
            type="number"
            label="Minimum file MiB"
            value={minSize}
            onChange={(e) => setMinSize(e.target.value)}
            inputProps={{ min: 0 }}
          />
          <TextField
            size="small"
            type="number"
            label="Maximum file MiB"
            value={maxSize}
            onChange={(e) => setMaxSize(e.target.value)}
            inputProps={{ min: 0 }}
          />
          <TextField
            size="small"
            type="date"
            label="Modified on/after (UTC)"
            value={after}
            onChange={(e) => setAfter(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            size="small"
            type="date"
            label="Modified on/before (UTC)"
            value={before}
            onChange={(e) => setBefore(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
        </Stack>
        {summary.data && (
          <Typography variant="body2">
            {summary.data.files.toLocaleString()} matching cached names ·{" "}
            {bytes(summary.data.bytes)} known bytes ·{" "}
            {summary.data.unknown_sizes} unknown sizes
          </Typography>
        )}
        {entries.isError && (
          <Alert severity="error">{String(entries.error)}</Alert>
        )}
        <Stack sx={{ maxHeight: 300, overflow: "auto" }} spacing={0.5}>
          {entries.data?.items.map((entry) => (
            <Typography
              key={entry.id}
              variant="body2"
              sx={{ overflowWrap: "anywhere" }}
            >
              {entry.path} ·{" "}
              {entry.size_bytes === null
                ? "size unavailable"
                : bytes(entry.size_bytes)}{" "}
              · observed {new Date(entry.observed * 1000).toLocaleString()}
              {entry.metadata_error ? ` · ${entry.metadata_error}` : ""}
            </Typography>
          ))}
        </Stack>
        <Stack direction="row" spacing={1}>
          <Button disabled={!cursor} onClick={() => setCursor(0)}>
            First page
          </Button>
          <Button
            disabled={entries.isFetching || !entries.data?.next_cursor}
            onClick={() => setCursor(entries.data!.next_cursor!)}
          >
            Next 100 names
          </Button>
        </Stack>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          useFlexGap
          sx={{
            flexWrap: "wrap",
            "& > .MuiTextField-root": {
              flex: { sm: "1 1 170px" },
              minWidth: { sm: 170 },
            },
          }}
        >
          <TextField
            size="small"
            type="number"
            label="Batch file limit"
            value={maxFiles}
            onChange={(e) => setMaxFiles(Number(e.target.value))}
            inputProps={{ min: 1, max: 10000 }}
          />
          <TextField
            size="small"
            type="number"
            label="Batch budget (MiB)"
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            inputProps={{ min: 1 }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={sample}
                onChange={(e) => setSample(e.target.checked)}
              />
            }
            label="Seeded sample by folder/type/size"
          />
          {sample && (
            <TextField
              size="small"
              label="Sample seed"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          )}
        </Stack>
        <FormControlLabel
          control={
            <Checkbox
              checked={partial}
              onChange={(e) => setPartial(e.target.checked)}
            />
          }
          label="I accept incomplete coverage for this batch"
        />
        <Button
          variant="outlined"
          disabled={
            busy ||
            !filtersReady ||
            !validBudgets ||
            (latest?.status !== "done" && !partial)
          }
          onClick={() =>
            void act(async () => {
              choose(
                await apiJson<Selection>("/api/volume/selections", {
                  method: "POST",
                  json: {
                    filters: {
                      ...JSON.parse(filter),
                      metadata_state: "known",
                      max_bytes: Math.min(
                        maxSize === ""
                          ? Infinity
                          : Math.floor(Number(maxSize) * 1024 * 1024),
                        50 * 1024 * 1024,
                      ),
                    },
                    max_files: maxFiles,
                    max_bytes: Math.round(budget * 1024 * 1024),
                    sample,
                    seed,
                    allow_partial: partial,
                  },
                }),
              );
            })
          }
        >
          Freeze selection for Intake
        </Button>
        <Typography variant="caption">
          Intake accepts up to 10,000 files per batch and 50 MiB per file.
          Processing pauses between files after one hour; resume in Activity.
          The optional embedding step updates the library index, including
          previously processed documents. Changed or unreadable files fail
          individually; the remaining files continue. Older observations outside
          the latest scan are excluded.
        </Typography>
        <Stack direction="row" spacing={1}>
          <TextField
            size="small"
            label="Restore selection ID"
            value={restoreId}
            onChange={(e) => setRestoreId(e.target.value)}
          />
          <Button
            disabled={busy || !/^\d+$/.test(restoreId)}
            onClick={() =>
              void act(async () => {
                choose(
                  await apiJson<Selection>(
                    `/api/volume/selections/${restoreId}`,
                  ),
                );
              })
            }
          >
            Restore frozen selection
          </Button>
        </Stack>
        {selection && (
          <Stack spacing={1}>
            <Alert severity={selection.count ? "success" : "warning"}>
              Frozen selection #{selection.id}: {selection.count} files ·{" "}
              {bytes(selection.bytes)}.{" "}
              {selection.count
                ? "Use the processing options and Start intake below. Changing filters does not alter this selection."
                : "No eligible files; adjust filters or budgets and freeze again."}
            </Alert>
            <Typography variant="caption">
              Coverage at selection:{" "}
              {(Array.isArray(JSON.parse(selection.coverage))
                ? JSON.parse(selection.coverage)
                : []
              )
                .map(
                  (r: { id: number; status: string }) =>
                    `scan #${r.id} ${r.status}`,
                )
                .join(" · ")}
            </Typography>
            <Stack sx={{ maxHeight: 180, overflow: "auto" }}>
              {frozen.data?.items.map((entry) => (
                <Typography key={entry.id} variant="body2">
                  {entry.path}
                </Typography>
              ))}
            </Stack>
            <Stack direction="row">
              <Button
                disabled={!frozenCursor}
                onClick={() => setFrozenCursor(0)}
              >
                First selected page
              </Button>
              <Button
                disabled={!frozen.data?.next_cursor}
                onClick={() => setFrozenCursor(frozen.data!.next_cursor!)}
              >
                Next selected page
              </Button>
              <Button
                onClick={() => {
                  setSelection(null);
                  onSelect(null);
                }}
              >
                Clear selection
              </Button>
            </Stack>
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}
