// src/hooks/useFolderArtifactSummary.ts
import { useQuery } from "@tanstack/react-query";

import { getScopeArtifacts } from "../api/scopes";
import type { FolderScopeDescriptor, ScopeArtifactsResponse } from "../api/types";

export function useFolderArtifactSummary(
  folder: FolderScopeDescriptor,
  enabled = true,
) {
  return useQuery<ScopeArtifactsResponse>({
    queryKey: ["scopes", "artifacts", "folder", folder.folder_id],
    queryFn: () =>
      getScopeArtifacts({
        scope: {
          scope_type: "folder",
          folder_id: folder.folder_id,
        },
      }),
    enabled: enabled && folder.folder_id.trim().length > 0,
  });
}