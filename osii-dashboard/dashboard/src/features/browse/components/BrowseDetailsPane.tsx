import { Alert, CircularProgress, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { listFolderScopes } from "../../../api/scopes";
import { useScopeArtifacts } from "../../../hooks/useScopeArtifacts";
import { folderBreadcrumbs, normalizeFolderPath } from "../contents";

export function BrowseDetailsPane({ path, sourceName }: { path: string; sourceName: string }) {
  const folders = useQuery({ queryKey: ["scopes", "folders"], queryFn: listFolderScopes });
  const findFolder = (candidate: string) => folders.data?.scopes.find(folder => normalizeFolderPath(folder.path) === candidate);
  const legacyPath = path.split("/")[0] === sourceName ? path.split("/").slice(1).join("/") : null;
  const folder = findFolder(path) ?? (legacyPath !== null ? findFolder(legacyPath) : undefined);
  const summary = useScopeArtifacts(
    folder ? { scope_type: "folder", folder_id: folder.folder_id } : { scope_type: "root" },
    Boolean(folder),
  );
  const preview = summary.data?.artifact_summary.synthesis_preview;

  return (
    <Stack spacing={1.2}>
      <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
        {folderBreadcrumbs(path).map(item => item.label).join(" / ")}
      </Typography>
      {(folders.isPending || summary.isLoading) && <CircularProgress size={18} aria-label="Loading folder details" />}
      {(folders.isError || summary.isError) && <Alert severity="warning">Could not load the folder summary.</Alert>}
      {preview && <>
        <Typography variant="subtitle2">Summary</Typography>
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{preview}</Typography>
      </>}
    </Stack>
  );
}
