import { apiJson } from "./client";

export type DeletionMode = "sidecar_only" | "source_and_sidecar";
export type ObjectDeletionPreview = {
  file_id: string;
  mode: DeletionMode;
  preview_token: string;
  object_file_count: number;
  object_bytes: number;
  source_path: string | null;
  source_size_bytes: number | null;
  source_will_be_deleted: boolean;
  source_will_remain: boolean;
  collections: Array<{ id: string; name: string }>;
  folders: Array<{ folder_id: string; path: string }>;
  aggregate_paths: string[];
  active_jobs: Array<{ id: string; run_id: string; status: string }>;
  history_run_ids: string[];
  indexes_rebuild_required: boolean;
};

export function previewObjectDeletion(fileId: string, mode: DeletionMode) {
  return apiJson<ObjectDeletionPreview>(`/api/objects/${encodeURIComponent(fileId)}/deletion-preview`, {
    method: "POST",
    json: { mode },
  });
}

export function deleteObject(fileId: string, payload: { mode: DeletionMode; preview_token: string; confirmation: string }) {
  return apiJson<{ ok: boolean; source_deleted: boolean }>(`/api/objects/${encodeURIComponent(fileId)}`, {
    method: "DELETE",
    json: payload,
  });
}
