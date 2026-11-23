// src/features/collections/components/CreateCollectionDialog.tsx
import { CollectionDetailsFields } from "./CollectionDetailsFields";
import { useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
} from "@mui/material";

import { useCreateCollection } from "../../../hooks/useCollections";

type CreateCollectionDialogProps = {
  open: boolean;
  onClose: () => void;
  onCreated?: (collectionId: string) => void;
};

export function CreateCollectionDialog({
  open,
  onClose,
  onCreated,
}: CreateCollectionDialogProps) {
  const createMutation = useCreateCollection();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleCreate = async () => {
    const result = await createMutation.mutateAsync({
      name: name.trim(),
      description: description.trim() || null,
    });

    onCreated?.(result.collection.id);
    setName("");
    setDescription("");
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Create Collection</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <CollectionDetailsFields name={name} description={description} onNameChange={setName} onDescriptionChange={setDescription} />

          {createMutation.isError ? (
            <Alert severity="error">
              {createMutation.error instanceof Error
                ? createMutation.error.message
                : "Failed to create collection."}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => void handleCreate()}
          disabled={!name.trim() || createMutation.isPending}
        >
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
}