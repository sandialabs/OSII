// src/hooks/useEditedObjectText.ts
import { useQuery } from "@tanstack/react-query";

import { getEditedObjectText } from "../api/editedText";
import type { EditedTextReadResponse } from "../api/types";

export function useEditedObjectText(fileId: string, enabled = true) {
  return useQuery<EditedTextReadResponse>({
    queryKey: ["objects", fileId, "edited-text"],
    queryFn: () => getEditedObjectText(fileId),
    enabled: enabled && fileId.trim().length > 0,
  });
}