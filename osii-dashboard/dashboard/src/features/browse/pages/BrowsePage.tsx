// src/features/browse/pages/BrowsePage.tsx
import { useMemo } from "react";
import { Alert, CircularProgress, Stack, Typography } from "@mui/material";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listFolderScopes } from "../../../api/scopes";
import type { FolderScopeDescriptor } from "../../../api/types";
import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import { toFileCardModel } from "../../../domain/files";
import { BrowseExplorer } from "../components/BrowseExplorer";
import { buildFileRoute } from "../../../utils/routes";
import { useBrowsingScope } from "../../../app/providers/BrowsingScopeProvider";
import { immediateFiles, immediateFolders, normalizeFolderPath } from "../contents";

function getRootFolder(scopes: FolderScopeDescriptor[]): FolderScopeDescriptor | null {
  return scopes.find((scope) => normalizeFolderPath(scope.path) === "") ?? null;
}

function getFolderById(
  scopes: FolderScopeDescriptor[],
  folderId: string,
): FolderScopeDescriptor | null {
  return scopes.find((scope) => scope.folder_id === folderId) ?? null;
}

function getBreadcrumbs(
  scopes: FolderScopeDescriptor[],
  current: FolderScopeDescriptor,
): FolderScopeDescriptor[] {
  if (!normalizeFolderPath(current.path)) {
    return [current];
  }

  const result: FolderScopeDescriptor[] = [];
  const parts = normalizeFolderPath(current.path).split("/");

  for (let i = 0; i <= parts.length; i += 1) {
    const partialPath = parts.slice(0, i).join("/");
    const match = scopes.find((scope) => normalizeFolderPath(scope.path) === partialPath);
    if (match) {
      result.push(match);
    }
  }

  if (result.length === 0) {
    return [current];
  }

  return result;
}

export function BrowsePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { setFolderScope } = useBrowsingScope();
  const view = searchParams.get("view") === "icons" ? "icons" : "list";

  const folderQuery = useQuery({
    queryKey: ["scopes", "folders"],
    queryFn: listFolderScopes,
  });

  const scopes = folderQuery.data?.scopes ?? [];
  const rootFolder = getRootFolder(scopes);
  const folderIdFromQuery = searchParams.get("folder_id");

  const currentFolder = useMemo(() => {
    if (folderIdFromQuery) {
      const explicit = getFolderById(scopes, folderIdFromQuery);
      if (explicit) return explicit;
    }
    return rootFolder;
  }, [folderIdFromQuery, scopes, rootFolder]);

  const summariesQuery = useScopeSummaries(
    currentFolder
      ? { scope_type: "folder", folder_id: currentFolder.folder_id }
      : { scope_type: "root" },
    Boolean(currentFolder),
  );

  const childFolders = useMemo(() => {
    if (!currentFolder) return [];
    return immediateFolders(scopes, currentFolder);
  }, [scopes, currentFolder]);

  const breadcrumbs = useMemo(() => {
    if (!currentFolder) return [];
    return getBreadcrumbs(scopes, currentFolder);
  }, [scopes, currentFolder]);

  const fileCards = useMemo(
    () => immediateFiles(summariesQuery.data?.summaries ?? [], currentFolder?.path ?? "").map(toFileCardModel),
    [summariesQuery.data?.summaries, currentFolder?.path],
  );

  const handleOpenFolder = (folder: FolderScopeDescriptor) => {
    setFolderScope(folder);

    const next = new URLSearchParams(searchParams);
    next.set("folder_id", folder.folder_id);
    setSearchParams(next);
  };

  if (folderQuery.isLoading) {
    return (
      <Stack direction="row" spacing={2} alignItems="center">
        <CircularProgress size={24} />
        <Typography>Loading browser…</Typography>
      </Stack>
    );
  }

  if (folderQuery.isError) {
    return <Alert severity="error">Failed to load folder hierarchy.</Alert>;
  }

  if (!currentFolder) {
    return <Alert severity="info">No folder root is available.</Alert>;
  }

  return <BrowseExplorer key={currentFolder.folder_id} currentFolder={currentFolder} breadcrumbs={breadcrumbs}
    onNavigate={id => { const folder = getFolderById(scopes, id); if (folder) handleOpenFolder(folder); }}
    folders={childFolders} files={fileCards} view={view}
    loading={summariesQuery.isLoading} error={summariesQuery.isError ? "Failed to load folder contents." : undefined}
    onChangeView={nextView => { const next = new URLSearchParams(searchParams); next.set("view", nextView); setSearchParams(next, { replace: true }); }}
    onOpenFolder={handleOpenFolder} onOpenFile={fileId => navigate(buildFileRoute({ fileId }))} />;
}
