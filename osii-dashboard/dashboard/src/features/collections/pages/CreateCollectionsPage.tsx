import { Alert, Button, Stack } from "@mui/material";
import { CreateCollectionsTool } from "../components/CreateCollectionsTool";
import { useCreateCollectionSelection } from "../../../hooks/useCreateCollectionSelection";
import { usePackageImport } from "../../../hooks/usePackageImport";

export function CreateCollectionsPage() {
  const create = useCreateCollectionSelection();
  const packageImport = usePackageImport();
  return (
    <Stack spacing={2}>
      <CreateCollectionsTool create={create} />
      <Button
        component="label"
        variant="outlined"
        sx={{ alignSelf: "start" }}
        disabled={packageImport.isPending}
      >
        {packageImport.isPending ? "Importing…" : "Import OSII package"}
        <input
          hidden
          type="file"
          accept=".zip,application/zip"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) packageImport.mutate(file);
          }}
        />
      </Button>
      {packageImport.isError && (
        <Alert severity="error">{(packageImport.error as Error).message}</Alert>
      )}
      {packageImport.data && (
        <Alert severity="success">
          Imported {packageImport.data.imported_file_ids.length} new object
          sidecar(s); found {packageImport.data.duplicate_file_ids.length}{" "}
          duplicate(s). Rebuild search and embeddings when ready.
        </Alert>
      )}
    </Stack>
  );
}
