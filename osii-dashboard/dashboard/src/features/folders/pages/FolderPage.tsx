// src/features/folders/pages/FolderPage.tsx
import { Alert, Stack, Typography } from "@mui/material";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listFolderScopes } from "../../../api/scopes";
import { ScopeFileBrowser } from "../../files/components/ScopeFileBrowser";
import { useBrowsingScope } from "../../../app/providers/BrowsingScopeProvider";
import { useEffect } from "react";
import { ScopeEnrichmentsPanel } from "../../files/components/ScopeEnrichmentsPanel";

export function FolderPage() {
  const { folderId } = useParams<{ folderId: string }>();
  const { setFolderScope } = useBrowsingScope();

  const { data } = useQuery({
    queryKey: ["scopes", "folders"],
    queryFn: listFolderScopes,
  });

  const folder = (data?.scopes ?? []).find((scope) => scope.folder_id === folderId);

  useEffect(() => {
    if (folder) {
      setFolderScope(folder);
    }
  }, [folder, setFolderScope]);

  if (!folderId) {
    return <Alert severity="error">Missing folder ID.</Alert>;
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>
          {folder?.label ?? "Folder"}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {folder?.path || folderId}
        </Typography>
      </Stack>

      <ScopeFileBrowser
        scope={{ scope_type: "folder", folder_id: folderId }}
        title="Files"
        subtitle={folder?.path || "Folder scope"}
        emptyMessage="No files were found in this folder scope."
      />
      <ScopeEnrichmentsPanel scope={{ scope_type: "folder", folder_id: folderId }} />
    </Stack>
  );
}
