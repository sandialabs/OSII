import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { apiJson } from "../api/client";
import type { FileDisplay } from "../domain/fileDisplay";
type SettingsResponse = { settings: FileDisplay; can_manage: boolean };
export function useFileDisplay() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["file-display"],
    queryFn: () => apiJson<SettingsResponse>("/api/files/display"),
    staleTime: 30_000,
  });
  const save = useMutation({
    mutationFn: (settings: FileDisplay) =>
      apiJson<SettingsResponse>("/api/files/display", {
        method: "PUT",
        json: settings,
      }),
    onSuccess: (data) => {
      client.setQueryData(["file-display"], data);
    },
  });
  return { query, save };
}
export type FilePreview = { text_preview: string; synthesis_preview: string; descriptive_title?: string | null };
export function useFilePreviews(ids: string[], includeTitles = false) {
  const groups: string[][] = [];
  for (let i = 0; i < ids.length; i += 48) groups.push(ids.slice(i, i + 48));
  const results = useQueries({
    queries: groups.map((file_ids) => ({
      queryKey: ["file-previews", file_ids, includeTitles],
      queryFn: ({ signal }) =>
        apiJson<{ items: Record<string, FilePreview> }>("/api/files/previews", {
          method: "POST",
          json: { file_ids, include_titles: includeTitles },
          signal,
        }),
      staleTime: 60_000,
    })),
  });
  return {
    items: Object.assign(
      {},
      ...results.map((result) => result.data?.items ?? {}),
    ) as Record<string, FilePreview>,
    failed: results.some((result) => result.isError),
  };
}
