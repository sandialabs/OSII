import { useEffect, useState } from "react";
import { Alert, Autocomplete, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { useCreateKeywordSet, useKeywordSets, useManualKeywords, useSaveManualKeywords } from "../../../hooks/useKeywords";
import { useObjectGovernance, useSaveObjectGovernance } from "../../../hooks/useGovernance";

export function ManualKeywordsDialog({ open, onClose, fileId }: { open: boolean; onClose: () => void; fileId: string }) {
  const manual = useManualKeywords(fileId);
  const sets = useKeywordSets();
  const save = useSaveManualKeywords(fileId);
  const createSet = useCreateKeywordSet();
  const governance = useObjectGovernance(fileId);
  const saveGovernance = useSaveObjectGovernance(fileId);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [sensitivityLabels, setSensitivityLabels] = useState<string[]>([]);
  const [handlingNotes, setHandlingNotes] = useState("");
  const [setName, setSetName] = useState("");
  const error = save.error ?? saveGovernance.error ?? createSet.error;

  useEffect(() => {
    if (open) {
      setKeywords(governance.data?.governance.tags ?? manual.data?.keywords ?? []);
      setSensitivityLabels(governance.data?.governance.sensitivity_labels ?? []);
      setHandlingNotes(governance.data?.governance.handling_notes ?? "");
    }
  }, [open, manual.data?.keywords, governance.data?.governance]);

  const addSet = (values: string[]) => {
    setKeywords((current) => [...new Map([...current, ...values].map((value) => [value.toLocaleLowerCase(), value])).values()]);
  };

  const handleSave = async () => {
    await Promise.all([
      save.mutateAsync(keywords),
      saveGovernance.mutateAsync({ sensitivity_labels: sensitivityLabels, tags: keywords, handling_notes: handlingNotes }),
    ]);
    onClose();
  };

  const handleCreateSet = async () => {
    await createSet.mutateAsync({ name: setName.trim(), keywords });
    setSetName("");
  };

  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
    <DialogTitle>Labels and tags</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">Sensitivity labels are portable awareness metadata, not access controls. Tags remain plain text so they can describe topics or local handling categories.</Typography>
        <Autocomplete multiple freeSolo options={["Public", "Internal", "PII", "CUI"]} value={sensitivityLabels} onChange={(_, values) => setSensitivityLabels(values.map(String))} renderTags={(values, getTagProps) => values.map((value, index) => <Chip color="warning" label={value} {...getTagProps({ index })} key={`${value}-${index}`} />)} renderInput={(params) => <TextField {...params} label="Sensitivity labels" placeholder="Choose or type a label" />} />
        <Autocomplete multiple freeSolo options={[]} value={keywords} onChange={(_, values) => setKeywords(values.map(String))} renderTags={(values, getTagProps) => values.map((value, index) => <Chip label={value} {...getTagProps({ index })} key={`${value}-${index}`} />)} renderInput={(params) => <TextField {...params} label="Tags" placeholder="Type a tag and press Enter" />} />
        <TextField label="Handling notes" value={handlingNotes} onChange={(event) => setHandlingNotes(event.target.value)} multiline minRows={2} placeholder="Optional human-readable instructions that should travel with this file" />
        {(sets.data?.keyword_sets ?? []).length > 0 ? <Stack spacing={1}>
          <Typography variant="subtitle2">Saved keyword sets</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{sets.data?.keyword_sets.map((set) => <Button key={set.id} size="small" variant="outlined" onClick={() => addSet(set.keywords)}>{set.name}</Button>)}</Stack>
        </Stack> : null}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Save current keywords as a set" value={setName} onChange={(event) => setSetName(event.target.value)} fullWidth />
          <Button variant="outlined" onClick={() => void handleCreateSet()} disabled={!setName.trim() || keywords.length === 0 || createSet.isPending}>Save set</Button>
        </Stack>
        {save.isError || saveGovernance.isError || createSet.isError ? <Alert severity="error">{error instanceof Error ? error.message : "Could not save labels and tags."}</Alert> : null}
      </Stack>
    </DialogContent>
    <DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" onClick={() => void handleSave()} disabled={save.isPending || saveGovernance.isPending}>Save labels and tags</Button></DialogActions>
  </Dialog>;
}
