// src/api/search.ts
import { apiJson } from "./client";
import type { SearchRequest, SearchScopedResponse } from "./types";

export async function search(payload: SearchRequest): Promise<SearchScopedResponse> {
  return apiJson<SearchScopedResponse>("/api/search", {
    method: "POST",
    json: payload,
  });
}