import { useState } from "react";
import { Alert, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Stack, Typography } from "@mui/material";
import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import { useAddCollectionMembers } from "../../../hooks/useCollections";

export function AddFilesToCollectionDialog({ open, onClose, collectionId }: { open: boolean; onClose: () => void; collectionId: string }) {
  const [selected, setSelected] = useState<string[]>([]);
  const files = useScopeSummaries({ scope_type: "root" }, open);
  const add = useAddCollectionMembers(collectionId);
  const toggle = (fileId: string) => setSelected((current) => current.includes(fileId) ? current.filter((id) => id !== fileId) : [...current, fileId]);
  const handleAdd = async () => {
    await add.mutateAsync({ file_ids: selected });
    setSelected([]);
    onClose();
  };
  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
    <DialogTitle>Add files to collection</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={1}>
        <Typography variant="body2" color="text.secondary">Choose processed files from the OSII sidecar. Adding them never moves or copies the originals.</Typography>
        {files.isLoading ? <Typography>Loading files…</Typography> : null}
        {files.isError ? <Alert severity="error">Could not load files.</Alert> : null}
        {(files.data?.summaries ?? []).map((file) => <FormControlLabel key={file.file_id} control={<Checkbox checked={selected.includes(file.file_id)} onChange={() => toggle(file.file_id)} />} label={`${file.filename ?? file.file_id}${file.source_relpath ? ` — ${file.source_relpath}` : ""}`} />)}
        {!files.isLoading && (files.data?.summaries ?? []).length === 0 ? <Typography color="text.secondary">No processed files are available.</Typography> : null}
        {add.isError ? <Alert severity="error">{add.error instanceof Error ? add.error.message : "Could not add files."}</Alert> : null}
      </Stack>
    </DialogContent>
    <DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" onClick={() => void handleAdd()} disabled={!selected.length || add.isPending}>Add selected</Button></DialogActions>
  </Dialog>;
}
