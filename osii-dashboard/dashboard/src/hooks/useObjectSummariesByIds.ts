// src/hooks/useObjectSummariesByIds.ts
import { useQuery } from "@tanstack/react-query";

import { getObjectSummaries } from "../api/objects";
import type { ObjectSummariesResponse } from "../api/types";

export function useObjectSummariesByIds(fileIds: string[], enabled = true) {
  return useQuery<ObjectSummariesResponse>({
    queryKey: ["objects", "summaries", fileIds],
    queryFn: () => getObjectSummaries({ file_ids: fileIds }),
    enabled: enabled && fileIds.length > 0,
  });
}