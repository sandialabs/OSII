// src/hooks/useSearch.ts
import { useQuery } from "@tanstack/react-query";

import { search } from "../api/search";
import type {
  ScopeDescribeRequest,
  SearchMode,
  SearchScopedResponse,
} from "../api/types";

export function useSearch(params: {
  query: string;
  mode?: SearchMode;
  topK?: number;
  scope: ScopeDescribeRequest;
  enabled?: boolean;
}) {
  const trimmed = params.query.trim();

  return useQuery<SearchScopedResponse>({
    queryKey: [
      "search",
      {
        query: trimmed,
        mode: params.mode ?? "semantic",
        topK: params.topK ?? 10,
        scope: params.scope,
        groupBy: "file",
      },
    ],
    queryFn: () =>
      search({
        query: trimmed,
        mode: params.mode,
        top_k: params.topK,
        scope: params.scope,
        group_by: "file",
      }),
    enabled: (params.enabled ?? true) && trimmed.length > 0,
  });
}