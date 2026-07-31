// src/hooks/useScopeSummaries.ts
import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { getScopeSummaries } from "../api/scopes";
import { listProcessingRuns } from "../api/queue";
import type { ScopeDescribeRequest, ScopeSummariesResponse } from "../api/types";

export function useScopeSummaries(
  scope: ScopeDescribeRequest,
  enabled = true,
) {
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
  const summaries = useQuery<ScopeSummariesResponse>({
    queryKey: ["scopes", "summaries", scope],
    queryFn: () => getScopeSummaries({ scope }),
    enabled,
  });

  useEffect(() => {
    if (!enabled || !progressKey) return;
    void summaries.refetch();
  }, [enabled, progressKey, summaries.refetch]);

  return summaries;
}
