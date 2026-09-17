// src/features/folders/pages/FolderPage.tsx
import { Alert, Stack, Tab, Tabs, Typography } from "@mui/material";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listFolderScopes } from "../../../api/scopes";
import { ScopeFileBrowser } from "../../files/components/ScopeFileBrowser";
import { useBrowsingScope } from "../../../app/providers/BrowsingScopeProvider";
import { useEffect, useState } from "react";
import { ScopeEnrichmentsPanel } from "../../files/components/ScopeEnrichmentsPanel";
import { ScopeWikiPanel } from "../../files/components/ScopeWikiPanel";

export function FolderPage() {
  const { folderId } = useParams<{ folderId: string }>();
  const { setFolderScope } = useBrowsingScope();
  const [enrichmentTab, setEnrichmentTab] = useState<"wiki" | "artifacts">("wiki");

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
      <Stack spacing={2}>
        <Typography variant="h6" fontWeight={700}>Folder enrichments</Typography>
        <Tabs
          value={enrichmentTab}
          onChange={(_, value: "wiki" | "artifacts") => setEnrichmentTab(value)}
          aria-label="Folder enrichment views"
        >
          <Tab value="wiki" label="Wiki" />
          <Tab value="artifacts" label="Other enrichments" />
        </Tabs>
        {enrichmentTab === "wiki" ? (
          <ScopeWikiPanel
            scope={{ scope_type: "folder", folder_id: folderId }}
            title={folder?.label ?? "Folder"}
          />
        ) : (
          <ScopeEnrichmentsPanel scope={{ scope_type: "folder", folder_id: folderId }} />
        )}
      </Stack>
    </Stack>
  );
}
