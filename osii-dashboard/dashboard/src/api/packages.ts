import { ApiError, buildApiUrl } from "./client";

export type PackageImportResult = {
  ok: boolean;
  collection_id: string;
  imported_file_ids: string[];
  duplicate_file_ids: string[];
  governance_merged_file_ids: string[];
  indexes_rebuild_required: boolean;
};

export async function importOsiiPackage(file: File): Promise<PackageImportResult> {
  const body = new FormData();
  body.append("package", file);
  const response = await fetch(buildApiUrl("/api/packages/import"), { method: "POST", body });
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `Import failed with status ${response.status}`;
    throw new ApiError(detail, response.status, data);
  }
  return data as PackageImportResult;
}
