// src/utils/routes.ts
import type { SearchMode } from "../api/types";

export const QUEUE_ACTIVITY_PATH = "/intake?tab=activity";

export function buildRunRoute(runId: string): string {
  return `/intake/runs/${encodeURIComponent(runId)}`;
}

export const SEARCH_INDEX_PATH = "/tools/search-index";
export const SUMMARIZE_FILE_PATH = "/tools/summary";
export const SUGGEST_METADATA_PATH = "/tools/metadata";
export const READ_FILES_PATH = "/tools/read-files";

export function buildScopeProcessorRoute(methodId: string): string {
  return `/tools/process/${encodeURIComponent(methodId)}`;
}

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
