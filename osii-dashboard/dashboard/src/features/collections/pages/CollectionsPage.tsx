// src/features/collections/pages/CollectionsPage.tsx
import {
  Alert,
  Button,
  CircularProgress,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";

import { useCollections } from "../../../hooks/useCollections";
import { CollectionCard } from "../components/CollectionCard";
import { usePackageImport } from "../../../hooks/usePackageImport";

export function CollectionsPage() {
  const { data, isLoading, isError, error } = useCollections();
  const packageImport = usePackageImport();

  const handlePackage = async (file: File | undefined) => {
    if (!file) return;
    await packageImport.mutateAsync(file);
  };

  return (
    <Stack spacing={2.5}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} justifyContent="space-between" alignItems={{ xs: "flex-start", sm: "center" }}>
        <Stack spacing={0.5}>
          <Typography variant="h5" fontWeight={700}>
            Collections
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Organize files into curated groups, or merge a manifest-validated OSII sidecar package. Original files are never included in sidecar packages.
          </Typography>
        </Stack>
        <Button component="label" variant="outlined" startIcon={<UploadFileOutlinedIcon />} disabled={packageImport.isPending}>
          {packageImport.isPending ? "Importing…" : "Import OSII package"}
          <input hidden type="file" accept=".zip,application/zip" onChange={(event) => void handlePackage(event.target.files?.[0])} />
        </Button>
      </Stack>

      {packageImport.isError ? <Alert severity="error">{packageImport.error instanceof Error ? packageImport.error.message : "Package import failed."}</Alert> : null}
      {packageImport.data ? <Alert severity="success">Imported {packageImport.data.imported_file_ids.length} new object sidecar(s); found {packageImport.data.duplicate_file_ids.length} duplicate(s) and merged awareness labels for {packageImport.data.governance_merged_file_ids.length}. Search and embedding indexes must be rebuilt.</Alert> : null}

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
