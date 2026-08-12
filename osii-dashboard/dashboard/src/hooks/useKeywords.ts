import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createKeywordSet, getKeywordSets, getManualKeywords, saveManualKeywords } from "../api/keywords";

export function useKeywordSets() {
  return useQuery({ queryKey: ["keyword-sets"], queryFn: getKeywordSets });
}

export function useCreateKeywordSet() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createKeywordSet,
    onSuccess: () => client.invalidateQueries({ queryKey: ["keyword-sets"] }),
  });
}

export function useManualKeywords(fileId: string) {
  return useQuery({ queryKey: ["manual-keywords", fileId], queryFn: () => getManualKeywords(fileId) });
}

export function useSaveManualKeywords(fileId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (keywords: string[]) => saveManualKeywords(fileId, keywords),
    onSuccess: () => client.invalidateQueries({ queryKey: ["manual-keywords", fileId] }),
  });
}
