import { useQuery } from "@tanstack/react-query";
import { getTopicMap, getRelatedDocuments } from "../../api/topics";
import type { ScopeDescribeRequest } from "../../api/types";

export function useTopicMap(scope: ScopeDescribeRequest) {
  return useQuery({ queryKey: ["topics", "map", scope],
    queryFn: ({ signal }) => getTopicMap(scope, signal), retry: false });
}

export function useRelatedDocuments(scope: ScopeDescribeRequest, fileId: string, indexId?: string) {
  return useQuery({ queryKey: ["topics", "related", scope, indexId, fileId],
    queryFn: ({ signal }) => getRelatedDocuments(scope, fileId, signal),
    enabled: !!fileId && !!indexId, retry: false });
}
