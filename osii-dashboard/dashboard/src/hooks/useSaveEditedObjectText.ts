// src/hooks/useSaveEditedObjectText.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { putEditedObjectText } from "../api/editedText";
import type {
  EditedTextWriteRequest,
  EditedTextWriteResponse,
} from "../api/types";

export function useSaveEditedObjectText(fileId: string) {
  const queryClient = useQueryClient();

  return useMutation<EditedTextWriteResponse, Error, EditedTextWriteRequest>({
    mutationFn: (payload) => putEditedObjectText(fileId, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "edited-text"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "preferred-text"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "texts"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "detail", fileId] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "summaries"] }),
        queryClient.invalidateQueries({ queryKey: ["scopes", "summaries"] }),
        queryClient.invalidateQueries({ queryKey: ["search"] }),
      ]);
    },
  });
}