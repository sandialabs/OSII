// src/hooks/useObject.ts
import { useQuery } from "@tanstack/react-query";

import { getObject } from "../api/objects";
import type { ObjectAggregate } from "../api/types";

export function useObject(fileId: string, enabled = true) {
  return useQuery<ObjectAggregate>({
    queryKey: ["objects", "detail", fileId],
    queryFn: () => getObject(fileId),
    enabled: enabled && fileId.trim().length > 0,
  });
}