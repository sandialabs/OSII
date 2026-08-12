import { apiJson } from "./client";

export type KeywordSet = { id: string; name: string; keywords: string[] };

export function getKeywordSets() {
  return apiJson<{ keyword_sets: KeywordSet[] }>("/api/keyword-sets");
}

export function createKeywordSet(payload: { name: string; keywords: string[] }) {
  return apiJson<{ keyword_set: KeywordSet }>("/api/keyword-sets", { method: "POST", json: payload });
}

export function getManualKeywords(fileId: string) {
  return apiJson<{ file_id: string; keywords: string[] }>(
    `/api/objects/${encodeURIComponent(fileId)}/keywords/manual`,
  );
}

export function saveManualKeywords(fileId: string, keywords: string[]) {
  return apiJson<{ file_id: string; keywords: string[] }>(
    `/api/objects/${encodeURIComponent(fileId)}/keywords/manual`,
    { method: "PUT", json: { keywords } },
  );
}
