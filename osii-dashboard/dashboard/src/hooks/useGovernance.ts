import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getObjectGovernance, saveObjectGovernance, type ObjectGovernance } from "../api/governance";

export function useObjectGovernance(fileId: string) {
  return useQuery({
    queryKey: ["object-governance", fileId],
    queryFn: () => getObjectGovernance(fileId),
    enabled: Boolean(fileId),
  });
}

export function useSaveObjectGovernance(fileId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Omit<ObjectGovernance, "updated_utc">) => saveObjectGovernance(fileId, payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["object-governance", fileId] });
      void client.invalidateQueries({ queryKey: ["object", fileId] });
    },
  });
}
