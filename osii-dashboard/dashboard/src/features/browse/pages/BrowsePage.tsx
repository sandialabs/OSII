// src/features/browse/pages/BrowsePage.tsx
import { useMemo, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
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
  const [detailsOpen, setDetailsOpen] = useState(false);
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

  const selection: BrowseSelection = currentFolder
    ? { kind: "folder", folder: currentFolder }
    : { kind: "none" };

  const handleOpenFolder = (folder: FolderScopeDescriptor) => {
    setFolderScope(folder);
    setDetailsOpen(false);

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
          Open a folder to see its contents. Only files in the current folder appear here.
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

        <Stack spacing={1.5} sx={{ minWidth: 0, width: "100%" }}>
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
              key={currentFolder.folder_id}
              folders={childFolders}
              files={fileCards}
              view={view}
              onChangeView={(nextView) => {
                const next = new URLSearchParams(searchParams);
                next.set("view", nextView);
                setSearchParams(next, { replace: true });
              }}
              onOpenFolder={handleOpenFolder}
              onOpenFile={(fileId: string) => navigate(buildFileRoute({ fileId }))}
            />
          )}
        </Stack>

      <Accordion expanded={detailsOpen} onChange={(_, expanded) => setDetailsOpen(expanded)} variant="outlined" disableGutters slotProps={{ transition: { unmountOnExit: true } }}>
        <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
          <Typography variant="body2">Folder details & synthesis</Typography>
        </AccordionSummary>
        <AccordionDetails><BrowseDetailsPane selection={selection} /></AccordionDetails>
      </Accordion>
    </Stack>
  );
}
