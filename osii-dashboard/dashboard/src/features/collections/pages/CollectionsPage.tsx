import {
  Alert,
  Button,
  CircularProgress,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { Link } from "react-router-dom";
import { useCollections } from "../../../hooks/useCollections";
import {
  CollectionSuggestions,
  useStarterCollections,
} from "../components/CollectionSuggestions";
import { useCreateCollectionSelection } from "../../../hooks/useCreateCollectionSelection";
import { CollectionCard } from "../components/CollectionCard";

export function CollectionsPage() {
  const { data, isLoading, isError, error } = useCollections();
  const collections = data?.collections ?? [];
  const showSuggestions = useStarterCollections(
    collections.length,
    !isLoading && !isError,
  );
  const create = useCreateCollectionSelection();
  return (
    <Stack spacing={2}>
      <Typography variant="h5" fontWeight={700}>
        Collections
      </Typography>
      {showSuggestions && <CollectionSuggestions create={create} />}
      {isLoading ? (
        <CircularProgress size={24} />
      ) : isError ? (
        <Alert severity="error">
          Failed to load collections.{" "}
          {error instanceof Error ? error.message : ""}
        </Alert>
      ) : collections.length ? (
        <Grid container spacing={1.75}>
          {collections.map((collection) => (
            <Grid item xs={12} sm={6} lg={4} xl={3} key={collection.id}>
              <CollectionCard collection={collection} />
            </Grid>
          ))}
        </Grid>
      ) : (
        <Stack spacing={1}>
          <Typography color="text.secondary">
            Collections are a convenient way to group documents.
          </Typography>
          <Button
            component={Link}
            to="/tools/collections"
            variant="contained"
            sx={{ alignSelf: "start" }}
          >
            Create Collections
          </Button>
        </Stack>
      )}
    </Stack>
  );
}
