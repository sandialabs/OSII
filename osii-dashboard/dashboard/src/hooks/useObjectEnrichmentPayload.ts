import { useQuery } from "@tanstack/react-query";

import { getObjectEnrichmentPayload } from "../api/enrichments";
import type { ObjectEnrichmentPayloadResponse } from "../api/types";

export function useObjectEnrichmentPayload(
  fileId: string,
  filename: string,
  enabled = true,
) {
  return useQuery<ObjectEnrichmentPayloadResponse>({
    queryKey: ["enrichments", "objects", fileId, filename],
    queryFn: () => getObjectEnrichmentPayload({ fileId, filename }),
    enabled: enabled && fileId.length > 0 && filename.length > 0,
  });
}

