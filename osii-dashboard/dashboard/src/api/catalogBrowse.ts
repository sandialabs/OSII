import { apiJson } from "./client";

export type BrowseSort = "name-asc" | "name-desc" | "modified-desc" | "size-desc";

type BrowseFolder = { kind: "folder"; name: string; path: string };
export type BrowseFile = {
  kind: "file";
  name: string;
  path: string;
  file_id: string;
  mime: string | null;
  size_bytes: number | null;
  mtime_utc: string | null;
};
export type BrowseEntry = BrowseFolder | BrowseFile;

export function browseCatalog(path: string, { query = "", sort = "name-asc", offset = 0, signal }: {
  query?: string; sort?: BrowseSort; offset?: number; signal?: AbortSignal;
} = {}) {
  const params = new URLSearchParams({ path, query, sort, offset: String(offset) });
  return apiJson<{ path: string; items: BrowseEntry[]; has_more: boolean; source_name: string }>(
    `/api/catalog/browse?${params}`, { signal },
  );
}
