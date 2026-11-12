import { useMemo, useState } from "react";
import { Button, Stack } from "@mui/material";
import { MetadataSearchDrawer } from "../home/components/MetadataSearchDrawer";
import {
  emptyFileFilters,
  fileFormat,
  filterFiles,
} from "../../domain/fileFilters";
import { FileGrid } from "../files/components/FileGrid";
import { BrowseExplorer } from "../browse/components/BrowseExplorer";
import { useSearchParams } from "react-router-dom";
import { immediateFolders, normalizeFolderPath } from "../browse/contents";
import type { FolderScopeDescriptor } from "../../api/types";
import type { FileCardModel } from "../../domain/files";
import type { Doc, Scope } from "./api";

/** Hosted transport data mapped into the same browse UI used by OSII-local. */
export function LibraryBrowser({
  docs,
  folders,
  scope,
  onScope,
  onOpen,
  selected,
  onToggle,
  flat,
  loading,
}: {
  flat: boolean;
  loading?: boolean;
  docs: Doc[];
  folders: { folder_id: string; path: string }[];
  scope: Scope;
  onScope: (scope: Scope) => void;
  onOpen: (id: string) => void;
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
}) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [filters, setFilters] = useState({ ...emptyFileFilters });
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "icons" ? "icons" : "list";
  const folder = (path: string): FolderScopeDescriptor => ({
    scope_type: "folder",
    scope_id: path || ".",
    folder_id: path || ".",
    path,
    label: path || "Root",
  });
  const path =
    scope.scope_type === "folder"
      ? normalizeFolderPath(scope.folder_id || "")
      : "";
  const parents = [folder("")];
  path
    .split("/")
    .filter(Boolean)
    .forEach((_, i, parts) =>
      parents.push(folder(parts.slice(0, i + 1).join("/"))),
    );
  const openFolder = (id: string) =>
    onScope(
      id === "."
        ? { scope_type: "root" }
        : { scope_type: "folder", folder_id: id },
    );
  const files: FileCardModel[] = docs.map((doc) => ({
    fileId: doc.file_id,
    title: doc.filename,
    subtitle: doc.source_relpath,
    mime:
      doc.media_type ||
      (doc.filename.toLowerCase().endsWith(".pdf") ? "application/pdf" : null),
    sourceFileRelpath: doc.source_relpath,
    sizeBytes: doc.size_bytes ?? null,
    modifiedAt: doc.modified_at ?? null,
    synthesisPreview: null,
    previewAvailable: true,
    hasPreferredText: doc.has_text ?? false,
    hasSynthesis: doc.has_synthesis ?? false,
    hasEnrichments: doc.has_enrichments ?? false,
    supportsMarkdownRender: false,
  }));
  const result = useMemo(() => filterFiles(files, filters), [files, filters]);
  const formats = [...new Set(files.map(fileFormat))].sort();
  const filtered = Object.keys(emptyFileFilters).some(
    (key) =>
      filters[key as keyof typeof filters] !==
      emptyFileFilters[key as keyof typeof filters],
  );
  if (flat)
    return (
      <Stack spacing={2}>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => setSearchOpen(true)}>
            Search metadata{filtered ? " · filters active" : ""}
          </Button>
          {filtered && (
            <Button onClick={() => setFilters({ ...emptyFileFilters })}>
              Clear filters
            </Button>
          )}
        </Stack>
        <FileGrid
          files={result.files}
          title="All Files"
          subtitle={`${result.files.length} of ${docs.length} loaded files`}
          emptyMessage={
            result.error || "No files match these metadata filters."
          }
          selectedIds={selected}
          onToggle={onToggle}
          onOpen={onOpen}
        />
        <MetadataSearchDrawer
          open={searchOpen}
          onClose={() => setSearchOpen(false)}
          filters={filters}
          onChange={setFilters}
          formats={formats}
          count={result.files.length}
          error={result.error}
          helperText={`Search the ${docs.length} loaded files by recorded metadata. Load more documents to include additional files. Source modification dates are UTC; earlier intakes may have no recorded date. No model is used.`}
        />
      </Stack>
    );
  return <BrowseExplorer loading={loading} key={path} currentFolder={folder(path)} breadcrumbs={parents} onNavigate={openFolder}
    context="folder" files={files} folders={immediateFolders(folders.map(f => folder(normalizeFolderPath(f.path))), folder(path))}
    view={view} onChangeView={value => { const next = new URLSearchParams(params); next.set("view", value); setParams(next, { replace: true }); }}
    onOpenFolder={f => openFolder(f.folder_id)} onOpenFile={onOpen} selectedIds={selected} onToggleFile={onToggle} />;
}
