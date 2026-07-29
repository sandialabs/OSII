// src/hooks/useScopeArtifacts.ts
import { useQuery } from "@tanstack/react-query";

import { getScopeArtifacts } from "../api/scopes";
import type {
  ScopeArtifactsResponse,
  ScopeDescribeRequest,
} from "../api/types";

export function useScopeArtifacts(
  scope: ScopeDescribeRequest,
  enabled = true,
) {
  return useQuery<ScopeArtifactsResponse>({
    queryKey: ["scopes", "artifacts", scope],
    queryFn: () => getScopeArtifacts({ scope }),
    enabled,
  });
}