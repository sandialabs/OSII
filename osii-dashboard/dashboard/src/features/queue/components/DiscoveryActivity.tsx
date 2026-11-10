import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import { apiJson } from "../../../api/client";
export type Source = { id: number; root: string; name: string };
export type Scan = {
  id: number;
  kind: string;
  source_id: number;
  status: string;
  observed_entries: number;
  known_bytes: number;
  metadata_errors: number;
  completed: number;
  failed: number;
  updated: number;
  created: number;
  error: string | null;
  issue_code?: string | null;
  current_paths?: string[];
};
export const isActiveScan = (run: Scan) =>
  ["queued", "running", "pausing", "cancelling"].includes(run.status);
export function useDiscoveryRuns() {
  return useQuery({
    queryKey: ["discovery", "runs"],
    queryFn: async () => {
      const [recent, active] = await Promise.all([
        apiJson<{ items: Scan[] }>(
          "/api/volume/runs?kind=scan&recent=true&limit=100",
        ),
        apiJson<{ items: Scan[] }>(
          "/api/volume/runs?kind=scan&active_only=true&limit=100",
        ),
      ]);
      return [
        ...new Map(
          [...recent.items, ...active.items]
            .filter((run) => run.kind === "scan")
            .map((run) => [run.id, run]),
        ).values(),
      ].sort((a, b) => b.id - a.id);
    },
    refetchInterval: 3000,
  });
}
export function ScanCard({
  run,
  root,
  compact = false,
}: {
  run: Scan;
  root?: string;
  compact?: boolean;
}) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const details = useQuery({
    queryKey: ["discovery", "run-details", run.id],
    queryFn: () => apiJson<Scan>(`/api/volume/runs/${run.id}`),
    enabled: expanded,
    refetchInterval: expanded && isActiveScan(run) ? 3000 : false,
  });
  const events = useQuery({
    queryKey: ["discovery", "events", run.id],
    queryFn: () =>
      apiJson<{ items: { id: number; path: string; message: string }[] }>(
        `/api/volume/runs/${run.id}/events?limit=100`,
      ),
    enabled: expanded,
    refetchInterval: expanded && isActiveScan(run) ? 5000 : false,
  });
  const control = async (action: string) => {
    setBusy(true);
    setError(null);
    try {
      await apiJson(`/api/volume/runs/${run.id}/${action}`, { method: "POST" });
      await client.invalidateQueries({ queryKey: ["discovery"] });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const issues = run.failed + run.metadata_errors;
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Stack
          direction="row"
          spacing={1}
          justifyContent="space-between"
          alignItems="center"
        >
          <Typography fontWeight={600}>
            Scanning{root ? ` · ${root}` : ` · #${run.id}`}
          </Typography>
          <Chip
            size="small"
            color={
              run.status === "done"
                ? issues
                  ? "warning"
                  : "success"
                : run.status === "error"
                  ? "error"
                  : "default"
            }
            label={
              run.status === "done"
                ? issues
                  ? "Completed with issues"
                  : "Completed"
                : run.status
            }
          />
        </Stack>
        <Typography variant="body2">
          {run.observed_entries.toLocaleString()} entries found
          {issues ? ` · ${issues} issues` : ""} · Last activity{" "}
          {new Date(run.updated * 1000).toLocaleString()}
        </Typography>
        {isActiveScan(run) && (
          <LinearProgress aria-label="Scan in progress; total unknown" />
        )}
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {["queued", "running"].includes(run.status) && (
            <Button disabled={busy} onClick={() => void control("pause")}>
              Pause
            </Button>
          )}
          {["paused", "error"].includes(run.status) && (
            <Button disabled={busy} onClick={() => void control("resume")}>
              {run.status === "error" ? "Retry failed" : "Resume"}
            </Button>
          )}
          {["running", "queued", "paused"].includes(run.status) && (
            <Button disabled={busy} onClick={() => void control("cancel")}>
              Cancel
            </Button>
          )}
          <Button onClick={() => setExpanded((value) => !value)}>
            {expanded ? "Hide details" : "View details & issues"}
          </Button>
        </Stack>
        {error && <Alert severity="error">{error}</Alert>}
        {expanded && (
          <Stack spacing={1}>
            {run.error && <Alert severity="warning">{run.error}</Alert>}
            <Typography variant="caption">
              Elapsed{" "}
              {Math.max(
                0,
                Math.floor(
                  (["done", "error", "cancelled"].includes(run.status)
                    ? run.updated
                    : Date.now() / 1000) - run.created,
                ),
              )}{" "}
              seconds including pauses · {run.completed} directory attempts
              completed
            </Typography>
            {details.data?.current_paths?.map((path) => (
              <Typography key={path} variant="caption">
                Reading: {path || "(root)"}
              </Typography>
            ))}
            {events.isError || details.isError ? (
              <Alert severity="error">
                Could not load scan details. Close and reopen to retry.
              </Alert>
            ) : null}
            {events.data?.items.map((event) => (
              <Typography
                key={event.id}
                variant="caption"
                sx={{ overflowWrap: "anywhere" }}
              >
                {event.path || "Location"}: {event.message}
              </Typography>
            ))}
            {!compact && (
              <Typography variant="caption">Scan #{run.id}</Typography>
            )}
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}
export function DiscoveryActivity() {
  const runs = useDiscoveryRuns();
  const sources = useQuery({
    queryKey: ["discovery", "sources"],
    queryFn: () => apiJson<{ items: Source[] }>("/api/volume/sources"),
  });
  const [older, setOlder] = useState<Scan[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [end, setEnd] = useState(false);
  const all = [
    ...new Map(
      [...older, ...(runs.data ?? [])].map((run) => [run.id, run]),
    ).values(),
  ].sort((a, b) => b.id - a.id);
  return (
    <Stack spacing={1.5}>
      <Typography fontWeight={700}>Discovery scans</Typography>
      {runs.isError && (
        <Alert
          severity="error"
          action={<Button onClick={() => void runs.refetch()}>Retry</Button>}
        >
          Scan queue unavailable.
        </Alert>
      )}
      {all.map((run) => {
        const root = sources.data?.items.find(
          (source) => source.id === run.source_id,
        )?.root;
        return isActiveScan(run) ? (
          <ScanCard key={`scan:${run.id}`} run={run} root={root} />
        ) : (
          <Accordion
            key={`scan:${run.id}`}
            disableGutters
            variant="outlined"
            slotProps={{ transition: { unmountOnExit: true } }}
          >
            <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
              <Stack
                direction="row"
                spacing={1}
                flexWrap="wrap"
                useFlexGap
                alignItems="center"
              >
                <Typography fontWeight={600}>
                  Scan · {root ?? run.id}
                </Typography>
                <Chip
                  size="small"
                  label={
                    run.status === "done"
                      ? run.failed || run.metadata_errors
                        ? "Completed with issues"
                        : "Completed"
                      : run.status
                  }
                  color={run.status === "error" ? "error" : "default"}
                />
                <Typography variant="caption">
                  {run.observed_entries.toLocaleString()} entries ·{" "}
                  {new Date(run.created * 1000).toLocaleString()}
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <ScanCard run={run} root={root} />
            </AccordionDetails>
          </Accordion>
        );
      })}
      {!all.length && !runs.isLoading && (
        <Typography color="text.secondary">No scans yet.</Typography>
      )}
      {error && <Alert severity="error">{error}</Alert>}
      {all.length > 0 && !end && (
        <Button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const result = await apiJson<{ items: Scan[] }>(
                `/api/volume/runs?kind=scan&recent=true&limit=100&before=${Math.min(...all.map((run) => run.id))}`,
              );
              setOlder((previous) => [
                ...previous,
                ...result.items.filter((run) => run.kind === "scan"),
              ]);
              setEnd(result.items.length < 100);
            } catch (e) {
              setError(String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          Older scans
        </Button>
      )}
    </Stack>
  );
}
