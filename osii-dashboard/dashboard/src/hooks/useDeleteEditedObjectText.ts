// src/hooks/useDeleteEditedObjectText.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteEditedObjectText } from "../api/editedText";
import type { EditedTextDeleteResponse } from "../api/types";

export function useDeleteEditedObjectText(fileId: string) {
  const queryClient = useQueryClient();

  return useMutation<EditedTextDeleteResponse, Error, void>({
    mutationFn: () => deleteEditedObjectText(fileId),
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