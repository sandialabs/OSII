import { useState } from "react";
import {
  Alert, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  FormControlLabel, IconButton, MenuItem, Stack, Switch, TextField, Tooltip,
} from "@mui/material";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import { defaultFileDisplay, type FileDisplay } from "../../../domain/fileDisplay";
import { useFileDisplay } from "../../../hooks/useFileDisplay";

export function FileDisplaySettings() {
  const { query, save } = useFileDisplay();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<FileDisplay | null>(null);
  const settings = draft ?? query.data?.settings ?? defaultFileDisplay;
  const close = () => { if (!save.isPending) setOpen(false); };

  if (query.data?.can_manage === false) return null;
  return (
    <>
      <Tooltip title="Display settings">
        <IconButton size="small" aria-label="Display settings" aria-haspopup="dialog"
          onClick={() => { setDraft(null); save.reset(); setOpen(true); }}>
          <SettingsOutlined fontSize="small" />
        </IconButton>
      </Tooltip>
      <Dialog open={open} onClose={close} fullWidth maxWidth="xs" aria-labelledby="file-display-title">
        <DialogTitle id="file-display-title">Display settings</DialogTitle>
        <DialogContent>
          {query.isPending ? <Alert severity="info">Loading display settings…</Alert> : query.isError ? (
            <Alert severity="error" action={<Button onClick={() => void query.refetch()}>Retry</Button>}>Could not load display settings.</Alert>
          ) : (
            <Stack spacing={2} sx={{ pt: 1 }}>
              <TextField select label="Default Files view" size="small" value={settings.view}
                onChange={event => setDraft({ ...settings, view: event.target.value as FileDisplay["view"] })}>
                <MenuItem value="thumbnails">Thumbnails</MenuItem>
                <MenuItem value="list">List</MenuItem>
              </TextField>
              <TextField select label="Tile label" size="small"
                value={settings.show_name ? settings.name_source ?? "filename" : "hidden"}
                onChange={event => {
                  const value = event.target.value as FileDisplay["name_source"] | "hidden";
                  setDraft({
                    ...settings, show_name: value !== "hidden",
                    name_source: value === "hidden" ? settings.name_source : value,
                  });
                }}>
                <MenuItem value="filename">Filename</MenuItem>
                <MenuItem value="descriptive_title">Descriptive title</MenuItem>
                <MenuItem value="hidden">Hidden</MenuItem>
              </TextField>
              <TextField select label="Detail line" size="small" value={settings.metadata}
                onChange={event => setDraft({ ...settings, metadata: event.target.value as FileDisplay["metadata"] })}>
                <MenuItem value="none">None</MenuItem>
                <MenuItem value="format">File type</MenuItem>
                <MenuItem value="modified">Modified date</MenuItem>
                <MenuItem value="path">Source path</MenuItem>
              </TextField>
              <FormControlLabel label="Show file size" control={<Switch checked={settings.show_size}
                onChange={(_, checked) => setDraft({ ...settings, show_size: checked })} />} />
              {save.isError && <Alert severity="error">{save.error.message}</Alert>}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={close} disabled={save.isPending}>Cancel</Button>
          <Button variant="contained" disabled={!query.data?.can_manage || save.isPending}
            onClick={() => save.mutate(settings, { onSuccess: () => setOpen(false) })}>
            Save defaults
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
