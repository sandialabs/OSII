import { useQuery } from "@tanstack/react-query";

import { getScopeEnrichmentPayload } from "../api/enrichments";
import type {
  ObjectEnrichmentPayloadResponse,
  ScopeDescribeRequest,
} from "../api/types";

export function useScopeEnrichmentPayload(
  scope: ScopeDescribeRequest,
  filename: string,
  enabled = true,
) {
  return useQuery<ObjectEnrichmentPayloadResponse>({
    queryKey: ["enrichments", "payload", scope, filename],
    queryFn: () => getScopeEnrichmentPayload({ scope, filename }),
    enabled: enabled && filename.length > 0,
  });
}

