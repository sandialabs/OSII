// src/features/collections/pages/CollectionsPage.tsx
import {
  Alert,
  CircularProgress,
  Grid,
  Stack,
  Typography,
} from "@mui/material";

import { useCollections } from "../../../hooks/useCollections";
import { CollectionCard } from "../components/CollectionCard";

export function CollectionsPage() {
  const { data, isLoading, isError, error } = useCollections();

  return (
    <Stack spacing={2.5}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>
          Collections
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Organize files into curated groups and quickly preview what each collection contains.
        </Typography>
      </Stack>

      {isLoading ? (
        <Stack direction="row" spacing={2} alignItems="center">
          <CircularProgress size={24} />
          <Typography>Loading collections…</Typography>
        </Stack>
      ) : isError ? (
        <Alert severity="error">
          Failed to load collections.
          {error instanceof Error ? ` ${error.message}` : ""}
        </Alert>
      ) : (data?.collections ?? []).length === 0 ? (
        <Typography color="text.secondary">No collections available.</Typography>
      ) : (
        <Grid container spacing={1.75}>
          {(data?.collections ?? []).map((collection) => (
            <Grid item xs={12} sm={6} lg={4} xl={3} key={collection.id}>
              <CollectionCard collection={collection} />
            </Grid>
          ))}
        </Grid>
      )}
    </Stack>
  );
}