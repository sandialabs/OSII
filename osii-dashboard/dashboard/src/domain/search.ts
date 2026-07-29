// src/domain/search.ts
import type { SearchScopedResult } from "../api/types";

export type SearchResultModel = {
  fileId: string;
  filename: string;
  sourceRelpath: string;
  snippet: string | null;
  score: number;
  mode: string | null;
  charStart: number | null;
  charEnd: number | null;
  collections: Array<{ id: string; name: string }>;
};

export function toSearchResultModel(result: SearchScopedResult): SearchResultModel {
  return {
    fileId: result.file_id,
    filename: result.filename ?? result.file_id,
    sourceRelpath: result.source_relpath ?? "",
    snippet: result.snippet ?? null,
    score: result.score,
    mode: result.match_type ?? null,
    charStart: result.char_start ?? null,
    charEnd: result.char_end ?? null,
    collections: result.collections.map((collection) => ({
      id: collection.id,
      name: collection.name,
    })),
  };
}