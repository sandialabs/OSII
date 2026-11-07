import { useState } from "react";
import { Stack } from "@mui/material";
import { BrowseGrid } from "../browse/components/BrowseGrid";
import { BrowseBreadcrumbs } from "../browse/components/BrowseBreadcrumbs";
import { immediateFolders, normalizeFolderPath } from "../browse/contents";
import type { FolderScopeDescriptor } from "../../api/types";
import type { FileCardModel } from "../../domain/files";
import type { Doc, Scope } from "./api";

/** Hosted transport data mapped into the same browse UI used by OSII-local. */
export function LibraryBrowser({ docs, folders, scope, onScope, onOpen, selected, onToggle }: {
  docs: Doc[]; folders: { folder_id: string; path: string }[]; scope: Scope;
  onScope: (scope: Scope) => void; onOpen: (id: string) => void;
  selected: ReadonlySet<string>; onToggle: (id: string) => void;
}) {
  const [view, setView] = useState<"list" | "icons">("icons");
  const folder = (path: string): FolderScopeDescriptor => ({ scope_type: "folder", scope_id: path || ".",
    folder_id: path || ".", path, label: path || "Root" });
  const path = scope.scope_type === "folder" ? normalizeFolderPath(scope.folder_id || "") : "";
  const parents = [folder("")];
  path.split("/").filter(Boolean).forEach((_, i, parts) => parents.push(folder(parts.slice(0, i + 1).join("/"))));
  const openFolder = (id: string) => onScope(id === "." ? { scope_type: "root" } : { scope_type: "folder", folder_id: id });
  const files: FileCardModel[] = docs.map(doc => ({ fileId: doc.file_id, title: doc.filename,
    subtitle: doc.source_relpath, mime: doc.media_type || (doc.filename.toLowerCase().endsWith(".pdf") ? "application/pdf" : null),
    sourceFileRelpath: doc.source_relpath, sizeBytes: doc.size_bytes ?? null, modifiedAt: doc.updated_at ?? null,
    synthesisPreview: null, previewAvailable: true, hasPreferredText: true, hasSynthesis: false,
    hasEnrichments: false, supportsMarkdownRender: false }));
  return <Stack spacing={2}>
    {scope.scope_type !== "collection" && <BrowseBreadcrumbs items={parents} onNavigate={openFolder} />}
    <BrowseGrid key={`${scope.scope_type}:${path}:${scope.collection_id || ""}`} files={files}
      folders={scope.scope_type === "collection" ? [] : immediateFolders(folders.map(f => folder(normalizeFolderPath(f.path))), folder(path))}
      view={view} onChangeView={setView} onOpenFolder={f => openFolder(f.folder_id)} onOpenFile={onOpen}
      selectedIds={selected} onToggleFile={onToggle} />
  </Stack>;
}
