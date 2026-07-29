// src/features/browse/pages/BrowsePage.tsx
import { useMemo } from "react";
import {
  Alert,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listFolderScopes } from "../../../api/scopes";
import type { FolderScopeDescriptor } from "../../../api/types";
import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import { toFileCardModel } from "../../../domain/files";
import { BrowseBreadcrumbs } from "../components/BrowseBreadcrumbs";
import { BrowseGrid } from "../components/BrowseGrid";
import {
  BrowseDetailsPane,
  type BrowseSelection,
} from "../components/BrowseDetailsPane";
import { buildFileRoute } from "../../../utils/routes";
import { useBrowsingScope } from "../../../app/providers/BrowsingScopeProvider";

function getRootFolder(scopes: FolderScopeDescriptor[]): FolderScopeDescriptor | null {
  return scopes.find((scope) => scope.path === "") ?? scopes[0] ?? null;
}

function getFolderById(
  scopes: FolderScopeDescriptor[],
  folderId: string,
): FolderScopeDescriptor | null {
  return scopes.find((scope) => scope.folder_id === folderId) ?? null;
}

function getImmediateChildFolders(
  scopes: FolderScopeDescriptor[],
  parent: FolderScopeDescriptor,
): FolderScopeDescriptor[] {
  const parentPath = parent.path;
  const parentDepth = parentPath ? parentPath.split("/").length : 0;

  return scopes
    .filter((scope) => {
      if (scope.folder_id === parent.folder_id) return false;

      const scopePath = scope.path;
      const scopeDepth = scopePath ? scopePath.split("/").length : 0;

      if (parentPath === "") {
        return scopeDepth === 1;
      }

      return (
        scopePath.startsWith(`${parentPath}/`) &&
        scopeDepth === parentDepth + 1
      );
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

function getBreadcrumbs(
  scopes: FolderScopeDescriptor[],
  current: FolderScopeDescriptor,
): FolderScopeDescriptor[] {
  if (!current.path) {
    return [current];
  }

  const result: FolderScopeDescriptor[] = [];
  const parts = current.path.split("/");

  for (let i = 0; i <= parts.length; i += 1) {
    const partialPath = parts.slice(0, i).join("/");
    const match = scopes.find((scope) => scope.path === partialPath);
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
    return getImmediateChildFolders(scopes, currentFolder);
  }, [scopes, currentFolder]);

  const breadcrumbs = useMemo(() => {
    if (!currentFolder) return [];
    return getBreadcrumbs(scopes, currentFolder);
  }, [scopes, currentFolder]);

  const fileCards = useMemo(
    () => (summariesQuery.data?.summaries ?? []).map(toFileCardModel),
    [summariesQuery.data?.summaries],
  );

  const selection: BrowseSelection = currentFolder
    ? { kind: "folder", folder: currentFolder }
    : { kind: "none" };

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

  return (
    <Stack spacing={1.75}>
      <Stack spacing={0.35}>
        <Typography variant="h5" fontWeight={700}>
          Browse
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Navigate files in their native folder hierarchy.
        </Typography>
      </Stack>

      <BrowseBreadcrumbs
        items={breadcrumbs}
        onNavigate={(folderId: string) => {
          const folder = getFolderById(scopes, folderId);
          if (folder) {
            handleOpenFolder(folder);
          }
        }}
      />

      <Stack
        direction={{ xs: "column", xl: "row" }}
        spacing={2}
        alignItems="flex-start"
      >
        <Stack spacing={1.5} sx={{ flex: 1, minWidth: 0 }}>
          {summariesQuery.isLoading ? (
            <Stack direction="row" spacing={2} alignItems="center">
              <CircularProgress size={24} />
              <Typography>Loading folder contents…</Typography>
            </Stack>
          ) : summariesQuery.isError ? (
            <Alert severity="error">
              Failed to load folder contents.
              {summariesQuery.error instanceof Error ? ` ${summariesQuery.error.message}` : ""}
            </Alert>
          ) : (
            <BrowseGrid
              folders={childFolders}
              files={fileCards}
              selectedFolderId={currentFolder.folder_id}
              onOpenFolder={handleOpenFolder}
              onOpenFile={(fileId: string) => navigate(buildFileRoute({ fileId }))}
            />
          )}
        </Stack>

        <Stack sx={{ width: { xs: "100%", xl: 320 }, flexShrink: 0 }}>
          <BrowseDetailsPane selection={selection} />
        </Stack>
      </Stack>
    </Stack>
  );
}