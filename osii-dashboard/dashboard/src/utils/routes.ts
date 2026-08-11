// src/utils/routes.ts
import type { SearchMode } from "../api/types";

export function buildFileRoute(params: {
  fileId: string;
  charStart?: number | null;
  charEnd?: number | null;
  page?: number | null;
  segmentId?: string | null;
}): string {
  const search = new URLSearchParams();

  if (params.charStart != null) {
    search.set("char_start", String(params.charStart));
  }

  if (params.charEnd != null) {
    search.set("char_end", String(params.charEnd));
  }

  if (params.page != null) {
    search.set("page", String(params.page));
  }

  if (params.segmentId) {
    search.set("segment_id", params.segmentId);
  }

  const qs = search.toString();
  return `/files/${encodeURIComponent(params.fileId)}${qs ? `?${qs}` : ""}`;
}

export function buildSearchRoute(params: {
  query?: string;
  mode?: SearchMode;
}): string {
  const search = new URLSearchParams();

  if (params.query?.trim()) {
    search.set("q", params.query.trim());
  }

  if (params.mode) {
    search.set("mode", params.mode);
  }

  const qs = search.toString();
  return `/search${qs ? `?${qs}` : ""}`;
}

export function buildFolderRoute(folderId: string): string {
  return `/folders/${encodeURIComponent(folderId)}`;
}

export function buildCollectionRoute(collectionId: string): string {
  return `/collections/${encodeURIComponent(collectionId)}`;
}
