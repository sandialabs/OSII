// src/hooks/useObjectSyntheses.ts
import { useQuery } from "@tanstack/react-query";

import { getObjectSyntheses } from "../api/objects";
import type { ObjectSynthesesResponse } from "../api/types";

export function useObjectSyntheses(fileId: string, enabled = true) {
  return useQuery<ObjectSynthesesResponse>({
    queryKey: ["objects", fileId, "syntheses"],
    queryFn: () => getObjectSyntheses(fileId),
    enabled: enabled && fileId.trim().length > 0,
  });
}