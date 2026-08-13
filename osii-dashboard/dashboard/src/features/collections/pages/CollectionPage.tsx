// src/features/collections/pages/CollectionPage.tsx
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import AddOutlinedIcon from "@mui/icons-material/AddOutlined";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import { useNavigate, useParams } from "react-router-dom";

import { useBrowsingScope } from "../../../app/providers/BrowsingScopeProvider";
import {
  useCollection,
  useDeleteCollection,
  useUpdateCollection,
} from "../../../hooks/useCollections";
import { CollectionFileGrid } from "../components/CollectionFileGrid";
import { ScopeEnrichmentsPanel } from "../../files/components/ScopeEnrichmentsPanel";
import { ScopeWikiPanel } from "../../files/components/ScopeWikiPanel";
import { AddFilesToCollectionDialog } from "../components/AddFilesToCollectionDialog";
import { ScopeSuggestions } from "../../../components/discovery/ScopeSuggestions";

export function CollectionPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  const navigate = useNavigate();
  const { setCollectionScope } = useBrowsingScope();

  const { data, isLoading, isError, error } = useCollection(
    collectionId ?? "",
    Boolean(collectionId),
  );

  const updateMutation = useUpdateCollection(collectionId ?? "");
  const deleteMutation = useDeleteCollection();

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [addFilesOpen, setAddFilesOpen] = useState(false);

  useEffect(() => {
    if (data?.collection) {
      setCollectionScope(data.collection.id, data.collection.name);
    }
  }, [data?.collection, setCollectionScope]);

  if (!collectionId) {
    return <Alert severity="error">Missing collection ID.</Alert>;
  }

  if (isLoading) {
    return (
      <Stack spacing={2}>
        <Typography>Loading collection…</Typography>
      </Stack>
    );
  }

  if (isError) {
    return (
      <Alert severity="error">
        Failed to load collection.
        {error instanceof Error ? ` ${error.message}` : ""}
      </Alert>
    );
  }

  if (!data) {
    return <Alert severity="info">Collection not found.</Alert>;
  }

  const handleOpenEdit = () => {
    setName(data.collection.name);
    setDescription(data.collection.description ?? "");
    setEditOpen(true);
  };

  const handleSave = async () => {
    await updateMutation.mutateAsync({
      name: name.trim(),
      description: description.trim() || null,
    });
    setEditOpen(false);
  };

  const handleDelete = async () => {
    await deleteMutation.mutateAsync(collectionId);
    setDeleteOpen(false);
    navigate("/collections");
  };

  const handleSearchCollection = () => {
    navigate(
      `/search?scope_type=collection&collection_id=${encodeURIComponent(collectionId)}&mode=semantic`,
    );
  };

  const handleChatCollection = () => {
    navigate(
      `/chat?scope_type=collection&collection_id=${encodeURIComponent(collectionId)}`,
    );
  };

  const handleSuggestedSearch = (keyword: string) => {
    const params = new URLSearchParams({
      q: keyword,
      mode: "hybrid",
      scope_type: "collection",
      collection_id: collectionId,
    });
    navigate(`/search?${params.toString()}`);
  };

  return (
    <>
      <Stack spacing={3}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={1.5}
          justifyContent="space-between"
          alignItems={{ xs: "flex-start", md: "center" }}
        >
          <Stack spacing={0.5}>
            <Typography variant="h5" fontWeight={700}>
              {data.collection.name}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {data.collection.description || "No description"}
            </Typography>
          </Stack>

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              variant="outlined"
              startIcon={<SearchOutlinedIcon />}
              onClick={handleSearchCollection}
            >
              Search Collection
            </Button>
            <Button
              variant="outlined"
              startIcon={<ChatOutlinedIcon />}
              onClick={handleChatCollection}
            >
              Chat Collection
            </Button>
            <Button variant="outlined" startIcon={<AddOutlinedIcon />} onClick={() => setAddFilesOpen(true)}>
              Add Files
            </Button>
            <Button
              variant="outlined"
              startIcon={<DownloadOutlinedIcon />}
              component="a"
              href={`/api/collections/${encodeURIComponent(collectionId)}/export`}
            >
              Export OSII Package
            </Button>
            <Button
              variant="outlined"
              startIcon={<EditOutlinedIcon />}
              onClick={handleOpenEdit}
            >
              Edit
            </Button>
            <Button
              variant="outlined"
              color="error"
              startIcon={<DeleteOutlineOutlinedIcon />}
              onClick={() => setDeleteOpen(true)}
            >
              Delete
            </Button>
          </Stack>
        </Stack>

        <ScopeSuggestions
          scope={{ scope_type: "collection", collection_id: collectionId }}
          compact
          onSelect={handleSuggestedSearch}
        />

        <ScopeWikiPanel
          scope={{ scope_type: "collection", collection_id: collectionId }}
          title={data.collection.name}
        />
        <CollectionFileGrid collectionId={collectionId} />
        <ScopeEnrichmentsPanel
          scope={{ scope_type: "collection", collection_id: collectionId }}
        />
      </Stack>

      <Dialog open={editOpen} onClose={() => setEditOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Edit Collection</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <TextField
              fullWidth
              label="Name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <TextField
              fullWidth
              label="Description"
              multiline
              minRows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />

            {updateMutation.isError ? (
              <Alert severity="error">
                {updateMutation.error instanceof Error
                  ? updateMutation.error.message
                  : "Failed to update collection."}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => void handleSave()}
            disabled={!name.trim() || updateMutation.isPending}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <AddFilesToCollectionDialog open={addFilesOpen} onClose={() => setAddFilesOpen(false)} collectionId={collectionId} />

      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Delete Collection</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2">
            Are you sure you want to delete <strong>{data.collection.name}</strong>?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => void handleDelete()}
            disabled={deleteMutation.isPending}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
