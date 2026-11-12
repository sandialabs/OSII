import { apiJson } from "./client";
import type { ScopeDescribeRequest } from "./types";

import type { TopicMap, RelatedDocuments } from "../features/topics/types";
export type { TopicDocument, TopicPoint, TopicIndex, TopicMap, RelatedDocuments } from "../features/topics/types";

export function getTopicMap(scope: ScopeDescribeRequest, signal?: AbortSignal) {
  return apiJson<TopicMap>("/api/topics/map", { method: "POST", json: { scope }, signal });
}
export function getRelatedDocuments(scope: ScopeDescribeRequest, fileId: string, signal?: AbortSignal) {
  return apiJson<RelatedDocuments>("/api/topics/related", { method: "POST", json: { scope, file_id: fileId }, signal });
}
