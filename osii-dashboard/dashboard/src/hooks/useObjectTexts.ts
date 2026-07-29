// src/hooks/useObjectTexts.ts
import { useQuery } from "@tanstack/react-query";

import { getObjectTexts } from "../api/objects";
import type { ObjectTextsResponse } from "../api/types";

export function useObjectTexts(fileId: string, enabled = true) {
  return useQuery<ObjectTextsResponse>({
    queryKey: ["objects", fileId, "texts"],
    queryFn: () => getObjectTexts(fileId),
    enabled: enabled && fileId.trim().length > 0,
  });
}