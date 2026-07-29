// src/hooks/useObjectPreferredText.ts
import { useQuery } from "@tanstack/react-query";

import { getPreferredObjectText } from "../api/objects";
import type { PreferredTextResponse } from "../api/types";

export function useObjectPreferredText(fileId: string, enabled = true) {
  return useQuery<PreferredTextResponse>({
    queryKey: ["objects", fileId, "preferred-text"],
    queryFn: () => getPreferredObjectText(fileId),
    enabled: enabled && fileId.trim().length > 0,
  });
}