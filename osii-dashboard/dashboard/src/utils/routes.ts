// src/utils/routes.ts
import type { ProcessingRun, ScopeDescribeRequest, SearchMode } from "../api/types";
import { READ_WIKIS_PATH } from "../domain/workbench";

export { CREATE_WIKI_PATH, READ_WIKIS_PATH } from "../domain/workbench";

export const QUEUE_ACTIVITY_PATH = "/intake?tab=activity";

export function buildRunRoute(runId: string): string {
  return `/intake/runs/${encodeURIComponent(runId)}`;
}

export const SEARCH_INDEX_PATH = "/tools/search-index";
export const SUMMARIZE_FILE_PATH = "/tools/summary";
export const SUGGEST_METADATA_PATH = "/tools/metadata";
export const READ_FILES_PATH = "/tools/read-files";

export function buildWikiRoute(path: string, scope?: ScopeDescribeRequest, selection?: { file?: string; method?: string }) {
  const query = new URLSearchParams();
  if (scope) {
    query.set("scope", scope.scope_type);
    if (scope.scope_type === "collection") query.set("id", scope.collection_id);
    if (scope.scope_type === "folder") query.set("id", scope.folder_id);
    if (scope.scope_type === "object") query.set("id", scope.file_id);
  }
  if (selection?.file) query.set("file", selection.file);
  if (selection?.method) query.set("method", selection.method);
  return query.size ? `${path}?${query}` : path;
}

export function wikiRouteScope(query: URLSearchParams): ScopeDescribeRequest | undefined {
  const id = query.get("id") ?? "";
  switch (query.get("scope")) {
    case "root": return { scope_type: "root" };
    case "collection": return { scope_type: "collection", collection_id: id };
    case "folder": return { scope_type: "folder", folder_id: id };
    case "object": return { scope_type: "object", file_id: id };
    default: return undefined;
  }
}

export function wikiRunRoute(run?: ProcessingRun) {
  if (run?.status !== "done" || !run.scope) return undefined;
  if (run.batch_progress?.reduction !== "wiki" && !["toolbox.readable-wiki", "toolbox.concept-entity-wiki"].includes(run.tool_id ?? "")) return undefined;
  return buildWikiRoute(READ_WIKIS_PATH, run.scope, { method: run.tool_id });
}

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
