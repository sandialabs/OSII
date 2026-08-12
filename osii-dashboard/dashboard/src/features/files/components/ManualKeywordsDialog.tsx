import { useEffect, useState } from "react";
import { Alert, Autocomplete, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { useCreateKeywordSet, useKeywordSets, useManualKeywords, useSaveManualKeywords } from "../../../hooks/useKeywords";

export function ManualKeywordsDialog({ open, onClose, fileId }: { open: boolean; onClose: () => void; fileId: string }) {
  const manual = useManualKeywords(fileId);
  const sets = useKeywordSets();
  const save = useSaveManualKeywords(fileId);
  const createSet = useCreateKeywordSet();
  const [keywords, setKeywords] = useState<string[]>([]);
  const [setName, setSetName] = useState("");
  const error = save.error ?? createSet.error;

  useEffect(() => {
    if (open) setKeywords(manual.data?.keywords ?? []);
  }, [open, manual.data?.keywords]);

  const addSet = (values: string[]) => {
    setKeywords((current) => [...new Map([...current, ...values].map((value) => [value.toLocaleLowerCase(), value])).values()]);
  };

  const handleSave = async () => {
    await save.mutateAsync(keywords);
    onClose();
  };

  const handleCreateSet = async () => {
    await createSet.mutateAsync({ name: setName.trim(), keywords });
    setSetName("");
  };

  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
    <DialogTitle>Manual keywords</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">Add your own markers, then reuse named sets for sensitivity labels or topics.</Typography>
        <Autocomplete multiple freeSolo options={[]} value={keywords} onChange={(_, values) => setKeywords(values.map(String))} renderTags={(values, getTagProps) => values.map((value, index) => <Chip label={value} {...getTagProps({ index })} key={`${value}-${index}`} />)} renderInput={(params) => <TextField {...params} label="Keywords" placeholder="Type a keyword and press Enter" />} />
        {(sets.data?.keyword_sets ?? []).length > 0 ? <Stack spacing={1}>
          <Typography variant="subtitle2">Saved keyword sets</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{sets.data?.keyword_sets.map((set) => <Button key={set.id} size="small" variant="outlined" onClick={() => addSet(set.keywords)}>{set.name}</Button>)}</Stack>
        </Stack> : null}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Save current keywords as a set" value={setName} onChange={(event) => setSetName(event.target.value)} fullWidth />
          <Button variant="outlined" onClick={() => void handleCreateSet()} disabled={!setName.trim() || keywords.length === 0 || createSet.isPending}>Save set</Button>
        </Stack>
        {save.isError || createSet.isError ? <Alert severity="error">{error instanceof Error ? error.message : "Could not save keywords."}</Alert> : null}
      </Stack>
    </DialogContent>
    <DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" onClick={() => void handleSave()} disabled={save.isPending}>Save keywords</Button></DialogActions>
  </Dialog>;
}
