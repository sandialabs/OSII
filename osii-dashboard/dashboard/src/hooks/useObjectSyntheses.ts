// src/hooks/useObjectSyntheses.ts
import type { DocumentMetadata } from "../api/documentMetadata";
import { useQuery } from "@tanstack/react-query";

import { getObjectSyntheses } from "../api/objects";
import type { ObjectSynthesesResponse } from "../api/types";

export function useObjectSyntheses(fileId: string, enabled = true) {
  return useQuery<ObjectSynthesesResponse & { document_metadata?: DocumentMetadata | null }>({
    queryKey: ["objects", fileId, "syntheses"],
    queryFn: () => getObjectSyntheses(fileId),
    enabled: enabled && fileId.trim().length > 0,
  });
}