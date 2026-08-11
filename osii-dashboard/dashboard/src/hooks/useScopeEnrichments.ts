// src/hooks/useScopeEnrichments.ts
import { useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { listEnrichments } from "../api/enrichments";
import { listProcessingRuns } from "../api/queue";
import type {
  EnrichmentsListResponse,
  ScopeDescribeRequest,
} from "../api/types";

export function useScopeEnrichments(
  scope: ScopeDescribeRequest,
  enabled = true,
) {
  const queryClient = useQueryClient();
  const processingRuns = useQuery({
    queryKey: ["processing-runs"],
    queryFn: listProcessingRuns,
    refetchInterval: (query) => query.state.data?.runs.some(
      (run) => ["queued", "pending", "running"].includes(run.status),
    ) ? 1_200 : 10_000,
  });
  const progressKey = useMemo(
    () => (processingRuns.data?.runs ?? [])
      .map((run) => `${run.id}:${run.completed ?? 0}:${run.status}`)
      .join("|"),
    [processingRuns.data?.runs],
  );
  const enrichments = useQuery<EnrichmentsListResponse>({
    queryKey: ["enrichments", "scope", scope],
    queryFn: () => listEnrichments(scope),
    enabled,
  });

  useEffect(() => {
    if (!enabled || !progressKey) return;
    void queryClient.invalidateQueries({ queryKey: ["enrichments"] });
  }, [enabled, progressKey, queryClient]);

  return enrichments;
}
