// src/hooks/useScopeSummaries.ts
import { useQuery } from "@tanstack/react-query";

import { getScopeSummaries } from "../api/scopes";
import type { ScopeDescribeRequest, ScopeSummariesResponse } from "../api/types";

export function useScopeSummaries(
  scope: ScopeDescribeRequest,
  enabled = true,
) {
  return useQuery<ScopeSummariesResponse>({
    queryKey: ["scopes", "summaries", scope],
    queryFn: () => getScopeSummaries({ scope }),
    enabled,
  });
}