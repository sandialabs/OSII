import { useState } from "react";
import { Button, Chip, List, ListItemButton, Paper, Stack, Typography } from "@mui/material";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { Link } from "react-router-dom";
import type { ProcessingRun } from "../../../api/types";
import { failedRunFiles, runHasFailures, runStatusLabel, runTitle } from "../../../domain/processingRun";
import { isActiveRun } from "../../../domain/workflow";
import { buildRunRoute } from "../../../utils/routes";

export function ProcessingActivity({ recentRuns, workerAvailable }: {
  recentRuns: ProcessingRun[];
  workerAvailable?: boolean;
}) {
  const [showOlder, setShowOlder] = useState(false);
  const active = recentRuns.filter(run => isActiveRun(run.status));
  const history = recentRuns.filter(run => !isActiveRun(run.status));
  const visibleRuns = showOlder ? recentRuns : [...active, ...history.slice(0, 5)];

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
          <Typography component="h2" variant="h6">Processing runs</Typography>
          <Chip size="small" color={workerAvailable === false ? "error" : workerAvailable ? "success" : "default"}
            label={workerAvailable === false ? "Worker unavailable" : workerAvailable ? "Worker connected" : "Checking worker"} />
        </Stack>
        {!recentRuns.length && <Typography color="text.secondary">No processing runs yet.</Typography>}
        {visibleRuns.length > 0 && (
          <List disablePadding aria-label="Processing runs">
            {visibleRuns.map(run => {
              const failed = failedRunFiles(run).length;
              return (
                <ListItemButton key={run.id} component={Link} to={buildRunRoute(run.id)} divider sx={{ gap: 1, flexWrap: "wrap" }}>
                  <Stack sx={{ flex: "1 1 180px", minWidth: 0 }}>
                    <Typography fontWeight={650} sx={{ overflowWrap: "anywhere" }}>{runTitle(run)}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {new Date(run.created_at).toLocaleString()}{run.total != null ? ` · ${run.completed ?? 0}/${run.total} finished` : ""}
                    </Typography>
                  </Stack>
                  <Chip size="small" label={runStatusLabel(run)} color={runHasFailures(run) ? "warning" : run.status === "done" ? "success" : "default"} />
                  {failed > 0 && <Typography variant="caption">{failed.toLocaleString()} with issues</Typography>}
                  <ChevronRightIcon fontSize="small" />
                </ListItemButton>
              );
            })}
          </List>
        )}
        {history.length > 5 && <Button onClick={() => setShowOlder(value => !value)} sx={{ alignSelf: "start" }}>
          {showOlder ? "Hide older runs" : `Show older runs (${history.length - 5})`}
        </Button>}
      </Stack>
    </Paper>
  );
}
