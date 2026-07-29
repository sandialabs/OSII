// src/hooks/useEnrichmentJob.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { runEnrichmentJob } from "../api/jobs";
import type { ScopeDescribeRequest } from "../api/types";

export function useEnrichmentJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      enricher_name: string;
      scope: ScopeDescribeRequest;
      enricher_config?: Record<string, unknown>;
    }) => runEnrichmentJob(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["enrichments"] }),
        queryClient.invalidateQueries({ queryKey: ["objects"] }),
        queryClient.invalidateQueries({ queryKey: ["scopes", "summaries"] }),
      ]);
    },
  });
}