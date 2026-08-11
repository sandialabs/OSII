// src/domain/search.ts
import type { SearchScopedResult } from "../api/types";

export type SearchResultModel = {
  fileId: string;
  filename: string;
  sourceRelpath: string;
  snippet: string | null;
  score: number;
  mode: string | null;
  chunkMethod: string | null;
  page: number | null;
  segmentId: string | null;
  overlapWithPrevious: number;
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
    chunkMethod: result.chunk_method ?? null,
    page: result.page ?? null,
    segmentId: result.segment_id ?? null,
    overlapWithPrevious:
      typeof result.source_origin?.overlap_with_previous === "number"
        ? result.source_origin.overlap_with_previous
        : 0,
    charStart: result.char_start ?? null,
    charEnd: result.char_end ?? null,
    collections: result.collections.map((collection) => ({
      id: collection.id,
      name: collection.name,
    })),
  };
}
