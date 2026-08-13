import { useState } from "react";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import {
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";

import type { ActivityHistoryEntry, ActivityHistoryKind } from "../../utils/activityHistory";

function scopeLabel(entry: ActivityHistoryEntry): string {
  if (entry.scope.scope_type === "root") return "All files";
  if (entry.scope.scope_type === "collection") return `Collection · ${entry.scope.collection_id}`;
  if (entry.scope.scope_type === "folder") return `Folder · ${entry.scope.folder_id}`;
  return `File · ${entry.scope.file_id}`;
}

export function RecentActivity({
  kind,
  entries,
  onSelect,
  onDelete,
  onClear,
}: {
  kind: ActivityHistoryKind;
  entries: ActivityHistoryEntry[];
  onSelect: (entry: ActivityHistoryEntry) => void;
  onDelete: (id: string) => void;
  onClear: () => void;
}) {
  const [confirmClear, setConfirmClear] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const title = kind === "search" ? "Recent searches" : "Recent questions";
  const visibleEntries = showAll ? entries : entries.slice(0, 5);

  return <>
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1.25}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
            <Stack direction="row" spacing={1} alignItems="center">
              <HistoryOutlinedIcon color="action" fontSize="small" />
              <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
            </Stack>
            {entries.length > 0 ? <Button size="small" color="inherit" onClick={() => setConfirmClear(true)}>Clear all</Button> : null}
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Stored only in this browser. OSII saves queries and prompts—not results, answers, or citations.
          </Typography>
          {entries.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {kind === "search" ? "Your recent searches will appear here." : "Questions you send will appear here for quick reuse."}
            </Typography>
          ) : (
            <Stack spacing={0.5}>
              {visibleEntries.map((entry) => (
                <Stack key={entry.id} direction="row" alignItems="center" spacing={0.5}>
                  <Button
                    color="inherit"
                    onClick={() => onSelect(entry)}
                    sx={{ flex: 1, justifyContent: "flex-start", textAlign: "left", textTransform: "none", py: 0.75 }}
                  >
                    <Stack alignItems="flex-start" sx={{ minWidth: 0 }}>
                      <Typography variant="body2" noWrap sx={{ maxWidth: "100%" }}>{entry.text}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {scopeLabel(entry)}{entry.mode ? ` · ${entry.mode}` : ""} · {new Date(entry.timestamp).toLocaleString()}
                      </Typography>
                    </Stack>
                  </Button>
                  <IconButton size="small" aria-label={`Delete ${entry.text} from history`} onClick={() => onDelete(entry.id)}>
                    <DeleteOutlineOutlinedIcon fontSize="small" />
                  </IconButton>
                </Stack>
              ))}
              {entries.length > 5 ? (
                <Button size="small" color="inherit" onClick={() => setShowAll((current) => !current)} sx={{ alignSelf: "flex-start" }}>
                  {showAll ? "Show less" : `Show all ${entries.length}`}
                </Button>
              ) : null}
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
    <Dialog open={confirmClear} onClose={() => setConfirmClear(false)} maxWidth="xs" fullWidth>
      <DialogTitle>Clear {title.toLowerCase()}?</DialogTitle>
      <DialogContent><Typography variant="body2">This removes the saved prompts from this browser only.</Typography></DialogContent>
      <DialogActions>
        <Button onClick={() => setConfirmClear(false)}>Cancel</Button>
        <Button color="error" onClick={() => { onClear(); setConfirmClear(false); }}>Clear all</Button>
      </DialogActions>
    </Dialog>
  </>;
}
