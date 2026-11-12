import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { apiJson } from "../../api/client";

type Source = { id: number; name: string; root: string };
type Entry = {
  id: number;
  source_id: number;
  path: string;
  size_bytes: number;
  suffix: string;
  revision: number;
  extraction_id: string | null;
  stale?: number;
};
type Page<T> = { items: T[]; next_cursor: number | null };
type Selection = { id: number; count: number; bytes: number; request: string };
type Run = {
  id: number;
  kind: string;
  status: string;
  completed: number;
  failed: number;
  error: string | null;
  source_id: number | null;
  selection_id: number | null;
};
type Summary = {
  files: number;
  bytes: number;
  extracted: number;
  formats: { suffix: string; files: number; bytes: number }[];
  scan_status: { id: number; status: string }[];
};
type Report = {
  metrics: {
    attempted: number;
    usable: number;
    needs_ocr: number;
    reused: number;
    errors: number;
    text_chars: number;
    seconds: number;
  };
  selection_coverage: number;
  current_matching_inventory: number;
  estimated_seconds_for_matching_files: number | null;
  estimate_note: string;
  strata: unknown[];
};
type Document = Entry & {
  text: string | null;
  sha256: string | null;
  response: string | null;
  history: { revision: number; extraction_id: string }[];
  products: { id: number; kind: string; stale: number }[];
};
type Filters = {
  source_id?: number;
  path: string;
  name: string;
  suffix: string;
  text_state?: string;
  min_bytes: number;
  max_bytes?: number;
  modified_after?: number;
  modified_before?: number;
};
const emptyFilters: Filters = { path: "", name: "", suffix: "", min_bytes: 0 };
const bytes = (value: number) =>
  value < 1024
    ? `${value} B`
    : value < 1024 ** 2
      ? `${(value / 1024).toFixed(1)} KiB`
      : value < 1024 ** 3
        ? `${(value / 1024 ** 2).toFixed(1)} MiB`
        : `${(value / 1024 ** 3).toFixed(1)} GiB`;
const params = (values: object) =>
  new URLSearchParams(
    Object.entries(values)
      .filter(([, value]) => value !== undefined)
      .map(([key, value]) => [key, String(value)]),
  ).toString();
const get = <T,>(path: string) => apiJson<T>(`/api/volume/${path}`);
const post = <T,>(path: string, json: Record<string, unknown> = {}) =>
  apiJson<T>(`/api/volume/${path}`, { method: "POST", json });

export default function VolumePage() {
  const client = useQueryClient();
  const [notice, setNotice] = useState("");
  const [root, setRoot] = useState("");
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [draft, setDraft] = useState<Filters>(emptyFilters);
  const [cursor, setCursor] = useState(0);
  const [folderCursor, setFolderCursor] = useState(0);
  const [selectionCursor, setSelectionCursor] = useState(0);
  const [runCursor, setRunCursor] = useState(0);
  const [eventCursor, setEventCursor] = useState(0);
  const [maxFiles, setMaxFiles] = useState(100);
  const [byteBudget, setByteBudget] = useState(1024 ** 3);
  const [seed, setSeed] = useState("osii");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [memberCursor, setMemberCursor] = useState(0);
  const [stage, setStage] = useState("extract");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:8092");
  const [config, setConfig] = useState("{}");
  const [seconds, setSeconds] = useState(3600);
  const [activeRun, setActiveRun] = useState<number | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [searchCursor, setSearchCursor] = useState(0);
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [productText, setProductText] = useState("");
  const refresh = () => client.invalidateQueries({ queryKey: ["volume"] });
  const action = useMutation({
    mutationFn: async (operation: () => Promise<unknown>) => operation(),
    onSuccess: () => {
      setNotice("");
      void refresh();
    },
    onError: (error: Error) => setNotice(error.message),
  });
  const act = (operation: () => Promise<unknown>) => action.mutate(operation);
  const sources = useQuery({
    queryKey: ["volume", "sources"],
    queryFn: () => get<{ items: Source[] }>("sources"),
  });
  const summary = useQuery({
    queryKey: ["volume", "summary", filters],
    queryFn: () => get<Summary>(`summary?${params(filters)}`),
  });
  const entries = useQuery({
    queryKey: ["volume", "entries", filters, cursor],
    queryFn: () =>
      get<Page<Entry>>(`entries?${params({ ...filters, cursor })}`),
  });
  const folders = useQuery({
    queryKey: [
      "volume",
      "folders",
      filters.source_id,
      filters.path,
      folderCursor,
    ],
    queryFn: () =>
      get<Page<{ id: number; path: string; status: string }>>(
        `folders?${params({ source_id: filters.source_id, parent: filters.path, cursor: folderCursor })}`,
      ),
    enabled: !!filters.source_id,
  });
  const selections = useQuery({
    queryKey: ["volume", "selections", selectionCursor],
    queryFn: () =>
      get<{ items: Selection[] }>(`selections?cursor=${selectionCursor}`),
  });
  const members = useQuery({
    queryKey: ["volume", "members", selection?.id, memberCursor],
    queryFn: () =>
      get<Page<Entry>>(
        `selections/${selection!.id}/entries?cursor=${memberCursor}`,
      ),
    enabled: !!selection,
  });
  const runs = useQuery({
    queryKey: ["volume", "runs", runCursor],
    queryFn: () => get<{ items: Run[] }>(`runs?cursor=${runCursor}`),
    refetchInterval: 5000,
  });
  const run = useQuery({
    queryKey: ["volume", "run", activeRun],
    queryFn: () => get<Run>(`runs/${activeRun}`),
    enabled: !!activeRun,
    refetchInterval: 3000,
  });
  const events = useQuery({
    queryKey: ["volume", "events", activeRun, eventCursor],
    queryFn: () =>
      get<{ items: { id: number; path: string; message: string }[] }>(
        `runs/${activeRun}/events?cursor=${eventCursor}`,
      ),
    enabled: !!activeRun,
    refetchInterval: 5000,
  });
  const results = useQuery({
    queryKey: ["volume", "search", search, searchCursor],
    queryFn: () =>
      get<Page<Entry & { snippet: string }>>(
        `search?${params({ q: search, cursor: searchCursor })}`,
      ),
    enabled: !!search,
  });
  const document = useQuery({
    queryKey: ["volume", "document", documentId],
    queryFn: () => get<Document>(`entries/${documentId}`),
    enabled: !!documentId,
  });
  const showRun = (id: number) => {
    setActiveRun(id);
    setEventCursor(0);
    setReport(null);
  };
  const choose = (item: Selection) => {
    setSelection(item);
    setMemberCursor(0);
  };
  const makeSelection = (sample: boolean) =>
    act(async () =>
      choose(
        await post<Selection>("selections", {
          filters,
          sample,
          seed,
          max_files: maxFiles,
          max_bytes: byteBudget,
        }),
      ),
    );
  const applyFilters = (value: Filters) => {
    setDraft(value);
    setFilters(value);
    setCursor(0);
    setFolderCursor(0);
  };
  const errors = [
    sources.error,
    summary.error,
    entries.error,
    runs.error,
    selections.error,
    members.error,
    folders.error,
    events.error,
    run.error,
    document.error,
    results.error,
  ].filter(Boolean);
  const extractionDetails: {
    processor: { display_name: string; version: string };
    segments: { id: string; source_origin: Record<string, unknown> }[];
    warnings: string[];
  } | null = document.data?.response
    ? JSON.parse(document.data.response)
    : null;

  return (
    <Box sx={{ maxWidth: 1500, mx: "auto", p: { xs: 2, md: 4 } }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="h4">File inventory</Typography>
          <Typography color="text.secondary">
            Scan names, sizes, formats, and dates before choosing what to process.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button component={Link} to="/intake">Open Intake</Button>
          <Button onClick={() => void refresh()}>Refresh inventory</Button>
        </Stack>
      </Stack>
      <Alert severity="info" sx={{ my: 2 }}>
        Metadata scans leave document contents unread. Use Intake to add files to
        the main library. The bounded processing and text search below apply to
        this inventory.
      </Alert>
      <Alert severity="info" sx={{ my: 2 }}>
        Counts describe observed files, not a point-in-time snapshot. Queued,
        running, paused, or failed scans have incomplete coverage. Totals are
        logical bytes and include duplicate files.
      </Alert>
      {notice && (
        <Alert severity="error" onClose={() => setNotice("")}>
          {notice}
        </Alert>
      )}
      {errors.map((error, index) => (
        <Alert severity="error" key={index}>
          {(error as Error).message}
        </Alert>
      ))}

      <Paper sx={{ p: 2, my: 2 }}>
        <Typography variant="h6">1. Sources and discovery</Typography>
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={1}
          sx={{ my: 2 }}
        >
          <TextField
            label="Source directory on the OSII host"
            value={root}
            onChange={(e) => setRoot(e.target.value)}
            fullWidth
          />
          <Button
            disabled={!root || action.isPending}
            onClick={() =>
              act(async () => {
                await post("sources", { root });
                setRoot("");
              })
            }
          >
            Register source
          </Button>
        </Stack>
        {sources.data?.items.map((source) => (
          <Stack
            key={source.id}
            direction="row"
            alignItems="center"
            spacing={2}
            sx={{ mb: 1 }}
          >
            <Typography sx={{ flex: 1, overflowWrap: "anywhere" }}>
              {source.name} · {source.root}
            </Typography>
            <Button
              onClick={() =>
                act(async () =>
                  showRun((await post<Run>(`sources/${source.id}/scan`)).id),
                )
              }
            >
              Scan metadata
            </Button>
          </Stack>
        ))}
        <Typography variant="body2" color="text.secondary">
          Discovery does not open file contents or call processors. Scanning
          continues independently of this browser.
        </Typography>
      </Paper>

      <Paper sx={{ p: 2, my: 2 }}>
        <Typography variant="h6">2. Explore and select</Typography>
        <Stack direction="row" flexWrap="wrap" gap={1} sx={{ my: 2 }}>
          <TextField
            select
            label="Source"
            sx={{ minWidth: 180 }}
            value={draft.source_id ?? ""}
            onChange={(e) =>
              setDraft({
                ...draft,
                source_id: e.target.value ? Number(e.target.value) : undefined,
              })
            }
          >
            <MenuItem value="">All sources</MenuItem>
            {sources.data?.items.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Folder or exact path"
            value={draft.path}
            onChange={(e) => setDraft({ ...draft, path: e.target.value })}
          />
          <TextField
            label="Filename contains"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <TextField
            label="Extension"
            value={draft.suffix}
            onChange={(e) => setDraft({ ...draft, suffix: e.target.value })}
          />
          <TextField
            select
            label="Text state"
            sx={{ minWidth: 160 }}
            value={draft.text_state ?? "any"}
            onChange={(e) => setDraft({ ...draft, text_state: e.target.value })}
          >
            {["any", "metadata_only", "extracted"].map((state) => (
              <MenuItem key={state} value={state}>
                {state.replace("_", " ")}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Minimum bytes"
            type="number"
            value={draft.min_bytes}
            onChange={(e) =>
              setDraft({ ...draft, min_bytes: Number(e.target.value) })
            }
          />
          <TextField
            label="Maximum bytes"
            type="number"
            value={draft.max_bytes ?? ""}
            onChange={(e) =>
              setDraft({
                ...draft,
                max_bytes: e.target.value ? Number(e.target.value) : undefined,
              })
            }
          />
          <TextField
            label="Modified from (UTC)"
            type="date"
            slotProps={{ inputLabel: { shrink: true } }}
            onChange={(e) =>
              setDraft({
                ...draft,
                modified_after: e.target.value
                  ? Date.parse(`${e.target.value}T00:00:00Z`) / 1000
                  : undefined,
              })
            }
          />
          <TextField
            label="Modified through (UTC)"
            type="date"
            slotProps={{ inputLabel: { shrink: true } }}
            onChange={(e) =>
              setDraft({
                ...draft,
                modified_before: e.target.value
                  ? Date.parse(`${e.target.value}T23:59:59Z`) / 1000
                  : undefined,
              })
            }
          />
          <Button variant="contained" onClick={() => applyFilters(draft)}>
            Apply filters
          </Button>
        </Stack>
        {summary.data && (
          <>
            <Typography>
              {summary.data.files.toLocaleString()} files ·{" "}
              {bytes(summary.data.bytes)} ·{" "}
              {summary.data.extracted.toLocaleString()} with a current
              extraction
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1} sx={{ my: 1 }}>
              {summary.data.scan_status.map((s) => (
                <Chip
                  key={s.id}
                  label={`Scan ${s.id}: ${s.status}`}
                  onClick={() => showRun(s.id)}
                />
              ))}
            </Stack>
            <Stack direction="row" flexWrap="wrap" gap={1} sx={{ my: 1 }}>
              {summary.data.formats.slice(0, 20).map((f) => (
                <Chip
                  key={f.suffix}
                  label={`${f.suffix || "(no extension)"} · ${f.files.toLocaleString()}`}
                />
              ))}
            </Stack>
          </>
        )}
        {filters.source_id && (
          <Stack direction="row" flexWrap="wrap" gap={1}>
            <Button
              onClick={() =>
                applyFilters({
                  ...filters,
                  path: filters.path.split("/").slice(0, -1).join("/"),
                })
              }
            >
              Parent folder
            </Button>
            {folders.data?.items.map((f) => (
              <Button
                key={f.id}
                onClick={() => applyFilters({ ...filters, path: f.path })}
              >
                {f.path.split("/").slice(-1)[0]}{" "}
                {f.status !== "present" ? `(${f.status})` : ""}
              </Button>
            ))}
            <Button disabled={!folderCursor} onClick={() => setFolderCursor(0)}>
              First folders
            </Button>
            <Button
              disabled={!folders.data?.next_cursor}
              onClick={() => setFolderCursor(folders.data!.next_cursor!)}
            >
              More folders
            </Button>
          </Stack>
        )}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Source path</TableCell>
              <TableCell>Size</TableCell>
              <TableCell>Evidence</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {entries.data?.items.map((e) => (
              <TableRow key={e.id}>
                <TableCell>
                  <Button
                    sx={{ textTransform: "none", overflowWrap: "anywhere" }}
                    onClick={() => setDocumentId(e.id)}
                  >
                    {e.source_id}: {e.path}
                  </Button>
                </TableCell>
                <TableCell>{bytes(e.size_bytes)}</TableCell>
                <TableCell>
                  {e.extraction_id ? "Extracted" : "Metadata only"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <Stack direction="row" spacing={1} sx={{ my: 1 }}>
          <Button disabled={!cursor} onClick={() => setCursor(0)}>
            First page
          </Button>
          <Button
            disabled={!entries.data?.next_cursor}
            onClick={() => setCursor(entries.data!.next_cursor!)}
          >
            Next page
          </Button>
        </Stack>
        <Divider sx={{ my: 2 }} />
        <Stack direction="row" flexWrap="wrap" gap={1}>
          <TextField
            label="Maximum selected files"
            type="number"
            value={maxFiles}
            onChange={(e) => setMaxFiles(Number(e.target.value))}
          />
          <TextField
            label="Selected byte budget"
            type="number"
            value={byteBudget}
            onChange={(e) => setByteBudget(Number(e.target.value))}
          />
          <TextField
            label="Sample seed"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          />
          <Button
            disabled={action.isPending}
            onClick={() => makeSelection(true)}
          >
            Preview stratified sample
          </Button>
          <Button
            disabled={action.isPending}
            onClick={() => makeSelection(false)}
          >
            Preview bounded selection
          </Button>
        </Stack>
        <Typography variant="body2" sx={{ mt: 1 }}>
          Sampling interleaves folders, formats, size bands, and
          modification-year bands. It selects at most two files per group,
          within both budgets. Previewing does not process files.
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={1} sx={{ my: 2 }}>
          {selections.data?.items.map((s) => (
            <Chip
              key={s.id}
              label={`Selection ${s.id}: ${s.count} files`}
              onClick={() => choose(s)}
            />
          ))}
          <Button
            disabled={!selectionCursor}
            onClick={() => setSelectionCursor(0)}
          >
            First selections
          </Button>
          <Button
            disabled={selections.data?.items.length !== 50}
            onClick={() =>
              setSelectionCursor(selections.data!.items.slice(-1)[0]!.id)
            }
          >
            More selections
          </Button>
        </Stack>
        {selection && (
          <Box>
            <Typography variant="subtitle1">
              Selection {selection.id} · {selection.count.toLocaleString()}{" "}
              files · {bytes(selection.bytes)}
            </Typography>
            <Box component="pre" sx={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
              {selection.request}
            </Box>
            {members.data?.items.map((e) => (
              <Typography key={e.id} variant="body2">
                {e.source_id}: {e.path}
                {e.stale ? " · STALE — recreate selection" : ""}
              </Typography>
            ))}
            <Button disabled={!memberCursor} onClick={() => setMemberCursor(0)}>
              First members
            </Button>
            <Button
              disabled={!members.data?.next_cursor}
              onClick={() => setMemberCursor(members.data!.next_cursor!)}
            >
              More members
            </Button>
          </Box>
        )}
      </Paper>

      <Paper sx={{ p: 2, my: 2 }}>
        <Typography variant="h6">3. Process selected evidence</Typography>
        <Typography variant="body2" sx={{ mb: 2 }}>
          Each stage is independent. Successful text survives later failures.
          Per-file input is limited to 50 MiB; larger files remain inventoried.
          Synthesis and enrichment process one selected document at a time.
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={1}>
          <TextField
            select
            label="Stage"
            value={stage}
            sx={{ minWidth: 150 }}
            onChange={(e) => {
              const s = e.target.value;
              setStage(s);
              setEndpoint(
                `http://127.0.0.1:${s === "ocr" ? 8080 : s === "synthesize" ? 8093 : s === "enrich" ? 8094 : 8092}`,
              );
            }}
          >
            {["extract", "ocr", "synthesize", "enrich"].map((s) => (
              <MenuItem key={s} value={s}>
                {s}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Processor API endpoint"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            sx={{ minWidth: 290 }}
          />
          <TextField
            label="Processor configuration (JSON)"
            value={config}
            onChange={(e) => setConfig(e.target.value)}
          />
          <TextField
            label="Run seconds budget"
            type="number"
            value={seconds}
            onChange={(e) => setSeconds(Number(e.target.value))}
          />
          <Button
            variant="contained"
            disabled={!selection?.count || action.isPending}
            onClick={() =>
              act(async () => {
                const settings: unknown = JSON.parse(config);
                if (
                  !settings ||
                  typeof settings !== "object" ||
                  Array.isArray(settings)
                )
                  throw new Error("Configuration must be a JSON object");
                showRun(
                  (
                    await post<Run>("runs", {
                      selection_id: selection!.id,
                      stage,
                      endpoint,
                      config: settings,
                      max_seconds: seconds,
                    })
                  ).id,
                );
              })
            }
          >
            Process selection {selection?.id ?? ""}
          </Button>
        </Stack>
        <Table size="small" sx={{ mt: 2 }}>
          <TableHead>
            <TableRow>
              <TableCell>Run</TableCell>
              <TableCell>Stage</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Completed units</TableCell>
              <TableCell>Failed units</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {runs.data?.items.map((r) => (
              <TableRow key={r.id}>
                <TableCell>
                  <Button onClick={() => showRun(r.id)}>{r.id}</Button>
                </TableCell>
                <TableCell>{r.kind}</TableCell>
                <TableCell>{r.status}</TableCell>
                <TableCell>{r.completed}</TableCell>
                <TableCell>{r.failed}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <Button disabled={!runCursor} onClick={() => setRunCursor(0)}>
          First runs
        </Button>
        <Button
          disabled={runs.data?.items.length !== 50}
          onClick={() => setRunCursor(runs.data!.items.slice(-1)[0]!.id)}
        >
          More runs
        </Button>
        {run.data && (
          <Box sx={{ mt: 2 }}>
            <Typography>
              Run {run.data.id} · {run.data.status} ·{" "}
              {run.data.kind === "scan"
                ? "completed units are directories"
                : "completed units are file attempts"}
            </Typography>
            {run.data.error && <Alert severity="error">{run.data.error}</Alert>}
            <Stack direction="row" spacing={1}>
              {["pause", "resume", "cancel"].map((a) => (
                <Button
                  key={a}
                  disabled={
                    action.isPending ||
                    (a === "resume"
                      ? !["paused", "error"].includes(run.data!.status)
                      : ![
                          "queued",
                          "running",
                          ...(a === "cancel" ? ["paused"] : []),
                        ].includes(run.data!.status))
                  }
                  onClick={() => act(() => post(`runs/${activeRun}/${a}`))}
                >
                  {a}
                </Button>
              ))}
              {run.data.kind !== "scan" && (
                <Button
                  onClick={() =>
                    act(async () =>
                      setReport(await get<Report>(`runs/${activeRun}/report`)),
                    )
                  }
                >
                  Sample / processing report
                </Button>
              )}
            </Stack>
            {events.data?.items.map((e) => (
              <Typography variant="body2" key={e.id}>
                {e.path}: {e.message}
              </Typography>
            ))}
            <Button disabled={!eventCursor} onClick={() => setEventCursor(0)}>
              First diagnostics
            </Button>
            <Button
              disabled={events.data?.items.length !== 100}
              onClick={() =>
                setEventCursor(events.data!.items.slice(-1)[0]!.id)
              }
            >
              More diagnostics
            </Button>
          </Box>
        )}
        {report && (
          <Box sx={{ mt: 2 }}>
            <Typography>
              {report.metrics.attempted} attempted · {report.metrics.usable}{" "}
              usable · {report.metrics.needs_ocr} need OCR or contain no text ·{" "}
              {report.metrics.errors} failed · {report.metrics.reused} reused
            </Typography>
            <Typography>
              {Math.round(report.selection_coverage * 100)}% of selection
              attempted · {report.metrics.text_chars.toLocaleString()} text
              characters · {report.metrics.seconds.toFixed(1)} processing
              seconds
            </Typography>
            {report.estimated_seconds_for_matching_files !== null && (
              <Typography>
                Rough time for{" "}
                {report.current_matching_inventory.toLocaleString()} matching
                files:{" "}
                {(report.estimated_seconds_for_matching_files / 3600).toFixed(
                  1,
                )}{" "}
                hours.
              </Typography>
            )}
            <Alert severity="warning">{report.estimate_note}</Alert>
            <Box component="pre" sx={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
              {JSON.stringify(report.strata, null, 2)}
            </Box>
          </Box>
        )}
      </Paper>

      <Paper sx={{ p: 2, my: 2 }}>
        <Typography variant="h6">4. Search extracted text</Typography>
        <Stack direction="row" spacing={1} sx={{ my: 2 }}>
          <TextField
            fullWidth
            label="Words, quoted phrases, AND / OR / NOT"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Button
            onClick={() => {
              setSearch(query);
              setSearchCursor(0);
            }}
          >
            Search
          </Button>
        </Stack>
        <Typography variant="body2">
          Results cover current extracted content only. Metadata-only, missing,
          and stale revisions are excluded. Results are paged by source entry.
        </Typography>
        {results.data?.items.map((e) => (
          <Box key={e.id} sx={{ my: 2 }}>
            <Button onClick={() => setDocumentId(e.id)}>
              {e.source_id}: {e.path}
            </Button>
            <Typography>{e.snippet}</Typography>
          </Box>
        ))}
        <Button disabled={!searchCursor} onClick={() => setSearchCursor(0)}>
          First results
        </Button>
        <Button
          disabled={!results.data?.next_cursor}
          onClick={() => setSearchCursor(results.data!.next_cursor!)}
        >
          More results
        </Button>
      </Paper>

      <Dialog
        open={documentId !== null}
        onClose={() => {
          setDocumentId(null);
          setProductText("");
        }}
        fullWidth
        maxWidth="lg"
      >
        <DialogTitle>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
          >
            <Typography component="span">
              {document.data?.path ?? "Loading evidence"}
            </Typography>
            <Button
              onClick={() => {
                setDocumentId(null);
                setProductText("");
              }}
            >
              Close
            </Button>
          </Stack>
        </DialogTitle>
        <DialogContent>
          {document.data && (
            <>
              <Typography>
                Source {document.data.source_id} · revision{" "}
                {document.data.revision} ·{" "}
                {document.data.sha256 ?? "not hashed"}
              </Typography>
              <Typography variant="body2">
                Extraction {document.data.extraction_id ?? "not available"}
              </Typography>
              {document.data.extraction_id && (
                <Button
                  href={`/api/volume/entries/${documentId}/original`}
                  target="_blank"
                  rel="noopener"
                >
                  Download verified original
                </Button>
              )}
              <Box
                component="pre"
                sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
              >
                {document.data.text?.slice(0, 100000) ??
                  "No current extracted text. Historical revisions are retained in the canonical database."}
              </Box>
              {document.data.text && document.data.text.length > 100000 && (
                <Alert severity="info">
                  Preview shows the first 100,000 characters. The API and CLI
                  retain the full text.
                </Alert>
              )}
              <Typography variant="subtitle1">Source locations</Typography>
              {extractionDetails && (
                <>
                  <Typography variant="body2">
                    {extractionDetails.processor.display_name} · version{" "}
                    {extractionDetails.processor.version} ·{" "}
                    {extractionDetails.segments.length} text segments
                  </Typography>
                  {extractionDetails.warnings.map((warning, i) => (
                    <Alert severity="info" key={i}>
                      {warning}
                    </Alert>
                  ))}
                  {extractionDetails.segments.slice(0, 20).map((segment) => (
                    <Typography key={segment.id} variant="body2">
                      {segment.id} · {JSON.stringify(segment.source_origin)}
                    </Typography>
                  ))}
                </>
              )}
              <Box component="details" sx={{ my: 2 }}>
                <Box component="summary" sx={{ cursor: "pointer" }}>
                  Extraction details
                </Box>
                <Box
                  component="pre"
                  sx={{
                    whiteSpace: "pre-wrap",
                    fontSize: 12,
                    overflowWrap: "anywhere",
                  }}
                >
                  {document.data.response
                    ? JSON.stringify(
                        JSON.parse(document.data.response),
                        null,
                        2,
                      ).slice(0, 20000)
                    : "No extraction"}
                </Box>
              </Box>
              <Typography variant="subtitle1">
                Recent extraction history
              </Typography>
              {document.data.history.map((h) => (
                <Button
                  key={`${h.revision}-${h.extraction_id}`}
                  onClick={() =>
                    act(async () => {
                      const extraction = await get<{ response: string }>(
                        `entries/${documentId}/extractions/${h.extraction_id}`,
                      );
                      setProductText(
                        JSON.stringify(
                          JSON.parse(extraction.response),
                          null,
                          2,
                        ),
                      );
                    })
                  }
                >
                  Revision {h.revision} · {h.extraction_id.slice(0, 12)}
                </Button>
              ))}
              <Typography variant="subtitle1">Recent products</Typography>
              {document.data.products.map((p) => (
                <Button
                  key={p.id}
                  onClick={() =>
                    act(async () => {
                      const item = await get<{
                        response: string;
                        stale: number;
                      }>(`products/${p.id}`);
                      setProductText(
                        `${item.stale ? "STALE — based on an older extraction\n" : ""}${JSON.stringify(JSON.parse(item.response), null, 2)}`,
                      );
                    })
                  }
                >
                  {p.kind} {p.id}
                  {p.stale ? " · stale" : ""}
                </Button>
              ))}
              {productText && (
                <Box
                  component="pre"
                  sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {productText.slice(0, 100000)}
                </Box>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
}
