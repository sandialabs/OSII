// src/features/collections/components/AddFileToCollectionDialog.tsx
import { useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";

import { useAddCollectionMembers, useCollections } from "../../../hooks/useCollections";
import { CreateCollectionDialog } from "./CreateCollectionDialog";

type AddFileToCollectionDialogProps = {
  open: boolean;
  onClose: () => void;
  fileId: string;
};

export function AddFileToCollectionDialog({
  open,
  onClose,
  fileId,
}: AddFileToCollectionDialogProps) {
  const { data } = useCollections();
  const [collectionId, setCollectionId] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const addMutation = useAddCollectionMembers(collectionId);

  const handleAdd = async () => {
    await addMutation.mutateAsync({
      file_ids: [fileId],
    });
    setCollectionId("");
    onClose();
  };

  return (
    <>
      <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
        <DialogTitle>Add File to Collection</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <TextField
              fullWidth
              select
              label="Collection"
              value={collectionId}
              onChange={(event) => setCollectionId(event.target.value)}
            >
              <MenuItem value="">Select a collection</MenuItem>
              {(data?.collections ?? []).map((collection) => (
                <MenuItem key={collection.id} value={collection.id}>
                  {collection.name}
                </MenuItem>
              ))}
            </TextField>

            <Button
              variant="outlined"
              onClick={() => setCreateOpen(true)}
            >
              Create New Collection
            </Button>

            {addMutation.isError ? (
              <Alert severity="error">
                {addMutation.error instanceof Error
                  ? addMutation.error.message
                  : "Failed to add file to collection."}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => void handleAdd()}
            disabled={!collectionId || addMutation.isPending}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>

      <CreateCollectionDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(newCollectionId) => {
          setCollectionId(newCollectionId);
          setCreateOpen(false);
        }}
      />
    </>
  );
}