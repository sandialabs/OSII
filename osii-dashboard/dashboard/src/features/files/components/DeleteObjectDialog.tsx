import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Radio, RadioGroup, Stack, TextField, Typography } from "@mui/material";
import { deleteObject, previewObjectDeletion, type DeletionMode } from "../../../api/objectDeletion";

export function DeleteObjectDialog({ open, onClose, onDeleted, fileId }: { open: boolean; onClose: () => void; onDeleted: () => void; fileId: string }) {
  const [mode, setMode] = useState<DeletionMode>("sidecar_only");
  const [confirmation, setConfirmation] = useState("");
  const preview = useMutation({ mutationFn: () => previewObjectDeletion(fileId, mode) });
  const deletion = useMutation({ mutationFn: () => deleteObject(fileId, { mode, preview_token: preview.data?.preview_token ?? "", confirmation }) });

  useEffect(() => {
    if (open) {
      setConfirmation("");
      preview.reset();
      deletion.reset();
      void preview.mutateAsync();
    }
    // Mutation objects are intentionally omitted; including them retriggers the preview after each state update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, fileId]);

  const handleDelete = async () => {
    await deletion.mutateAsync();
    onDeleted();
  };

  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
    <DialogTitle>Delete file data</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2}>
        <Alert severity="warning">Deletion is permanent. OSII will remove affected aggregate products and indexes so they cannot retain excerpts from this file.</Alert>
        <RadioGroup value={mode} onChange={(event) => setMode(event.target.value as DeletionMode)}>
          <FormControlLabel value="sidecar_only" control={<Radio />} label="Remove OSII data only (keep the original file)" />
          <FormControlLabel value="source_and_sidecar" control={<Radio />} label="Remove the original file and all OSII data" />
        </RadioGroup>
        {preview.isPending ? <Typography variant="body2">Checking impact…</Typography> : null}
        {preview.data ? <Stack spacing={0.5}>
          <Typography variant="subtitle2">Impact preview</Typography>
          <Typography variant="body2">{preview.data.object_file_count} object-sidecar files; {preview.data.collections.length} collections; {preview.data.folders.length} folders.</Typography>
          <Typography variant="body2">{preview.data.aggregate_paths.length} aggregate products and {preview.data.history_run_ids.length} Activity run record(s) will be removed. {preview.data.indexes_rebuild_required ? "Search/embedding indexes will require rebuilding." : "No current index files were found."}</Typography>
          <Typography variant="body2">Original: {preview.data.source_path ? (preview.data.source_will_be_deleted ? "will be deleted" : "will remain") : "not found"}.</Typography>
          {preview.data.active_jobs.length ? <Alert severity="error">An Intake job still references this file. Wait for it to finish before deleting.</Alert> : null}
        </Stack> : null}
        <TextField label="Type the full file ID to confirm" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} helperText={fileId} fullWidth />
        {preview.isError || deletion.isError ? <Alert severity="error">{(preview.error ?? deletion.error) instanceof Error ? (preview.error ?? deletion.error)?.message : "Deletion failed."}</Alert> : null}
      </Stack>
    </DialogContent>
    <DialogActions><Button onClick={onClose}>Cancel</Button><Button color="error" variant="contained" onClick={() => void handleDelete()} disabled={!preview.data || confirmation !== fileId || Boolean(preview.data.active_jobs.length) || deletion.isPending}>Delete permanently</Button></DialogActions>
  </Dialog>;
}
