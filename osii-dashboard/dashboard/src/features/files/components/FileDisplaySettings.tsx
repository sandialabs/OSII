import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
} from "@mui/material";
import {
  defaultFileDisplay,
  type FileDisplay,
} from "../../../domain/fileDisplay";
import { useFileDisplay } from "../../../hooks/useFileDisplay";
export function FileDisplaySettings() {
  const { query, save } = useFileDisplay();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<FileDisplay>(defaultFileDisplay);
  useEffect(() => {
    if (open && query.data) setDraft(query.data.settings);
  }, [open, query.data]);
  if (!query.data?.can_manage)
    return query.isError ? (
      <Button onClick={() => void query.refetch()}>
        Retry display settings
      </Button>
    ) : null;
  return (
    <>
      <Button size="small" onClick={() => setOpen(true)}>
        Display settings
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Library display settings</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              select
              label="Default Files view"
              size="small"
              value={draft.view}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  view: event.target.value as FileDisplay["view"],
                })
              }
            >
              <MenuItem value="thumbnails">Thumbnails</MenuItem>
              <MenuItem value="list">Simple list</MenuItem>
            </TextField>
            <FormControlLabel
              control={
                <Switch
                  checked={draft.show_name}
                  onChange={(_, checked) =>
                    setDraft({ ...draft, show_name: checked })
                  }
                />
              }
              label="Show document name prominently"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={draft.show_size}
                  onChange={(_, checked) =>
                    setDraft({ ...draft, show_size: checked })
                  }
                />
              }
              label="Show file size"
            />
            <TextField
              select
              label="Small metadata line"
              size="small"
              value={draft.metadata}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  metadata: event.target.value as FileDisplay["metadata"],
                })
              }
            >
              {[
                ["none", "None"],
                ["format", "File type"],
                ["modified", "Modified date"],
                ["path", "Source path"],
              ].map(([value, label]) => (
                <MenuItem key={value} value={value}>
                  {label}
                </MenuItem>
              ))}
            </TextField>
            <Alert severity="info">
              These defaults apply to the whole library and every user.
            </Alert>
            {save.isError && (
              <Alert severity="error">{(save.error as Error).message}</Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={save.isPending}
            onClick={() =>
              save.mutate(draft, { onSuccess: () => setOpen(false) })
            }
          >
            Save defaults
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
