// src/hooks/useScopeEnrichments.ts
import { useQuery } from "@tanstack/react-query";

import { listEnrichments } from "../api/enrichments";
import type {
  EnrichmentsListResponse,
  ScopeDescribeRequest,
} from "../api/types";

export function useScopeEnrichments(
  scope: ScopeDescribeRequest,
  enabled = true,
) {
  return useQuery<EnrichmentsListResponse>({
    queryKey: ["enrichments", "scope", scope],
    queryFn: () => listEnrichments(scope),
    enabled,
  });
}