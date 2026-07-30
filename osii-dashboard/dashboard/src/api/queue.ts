import { apiJson, buildApiUrl } from "./client";
import type {
  IntakeResolveResponse,
  ProcessingRun,
  ProcessorEndpoint,
  QueueBrowseResponse,
  UploadResponse,
} from "./types";

export async function browseIntake(
  path?: string,
  includePatterns = "",
  excludePatterns = "",
  showHidden = false,
): Promise<QueueBrowseResponse> {
  const params = new URLSearchParams();
  if (path) params.set("path", path);
  if (includePatterns) params.set("include_patterns", includePatterns);
  if (excludePatterns) params.set("exclude_patterns", excludePatterns);
  if (showHidden) params.set("show_hidden", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiJson<QueueBrowseResponse>(`/api/browse${suffix}`);
}

export async function uploadQueueFiles(files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const response = await fetch(buildApiUrl("/api/uploads"), { method: "POST", body: form });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail ?? "Upload failed");
  return data as UploadResponse;
}

export async function createProcessingRun(payload: Record<string, unknown>): Promise<ProcessingRun> {
  return apiJson<ProcessingRun>("/api/runs", { method: "POST", json: payload });
}

export async function resolveIntake(payload: Record<string, unknown>): Promise<IntakeResolveResponse> {
  return apiJson<IntakeResolveResponse>("/api/resolve", { method: "POST", json: payload });
}

export async function listProcessingRuns(): Promise<{ runs: ProcessingRun[]; queue: Array<Record<string, unknown>> }> {
  return apiJson("/api/runs");
}

export async function listProcessorEndpoints(): Promise<{ processors: ProcessorEndpoint[] }> {
  return apiJson("/api/admin/processors");
}

export async function createProcessorEndpoint(payload: Omit<ProcessorEndpoint, "id"> & { id?: string }) {
  return apiJson<{ processor: ProcessorEndpoint }>("/api/admin/processors", { method: "POST", json: payload });
}

export async function checkProcessorEndpoint(id: string, test = false) {
  return apiJson<{ ok: boolean; status: number | null; detail: string }>(
    `/api/admin/processors/${encodeURIComponent(id)}/${test ? "test" : "health"}`,
    { method: "POST", json: {} },
  );
}
