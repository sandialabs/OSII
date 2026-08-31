import { apiJson, buildApiUrl } from "./client";
import type {
  IntakeResolveResponse,
  IntakeReadiness,
  ProcessingRun,
  ProcessorEndpoint,
  ModelProvider,
  ModelProviderHealth,
  ModelPullJob,
  OllamaRecommendation,
  QueueBrowseResponse,
  SourceRescanResponse,
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

export async function getIntakeReadiness(): Promise<IntakeReadiness> {
  return apiJson<IntakeReadiness>("/api/intake/readiness");
}

export async function rescanSourcePaths(apply = false): Promise<SourceRescanResponse> {
  return apiJson<SourceRescanResponse>("/api/intake/rescan-sources", {
    method: "POST",
    json: { apply },
  });
}

export async function getProcessorSettings(): Promise<{ settings: Record<string, Record<string, unknown>> }> {
  return apiJson("/api/admin/processor-settings");
}

export async function saveProcessorSettings(processorName: string, config: Record<string, unknown>) {
  return apiJson<{ processor_name: string; config: Record<string, unknown> }>(
    `/api/admin/processor-settings/${encodeURIComponent(processorName)}`,
    { method: "PUT", json: { config } },
  );
}

export async function listProcessingRuns(): Promise<{ runs: ProcessingRun[]; queue: Array<Record<string, unknown>> }> {
  return apiJson("/api/runs");
}

export async function controlProcessingRun(
  runId: string,
  action: "pause" | "resume" | "cancel",
): Promise<{ run_id: string; status: string; queue_status: string }> {
  return apiJson(`/api/runs/${encodeURIComponent(runId)}/${action}`, {
    method: "POST",
    json: {},
  });
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

export async function listModelProviders(): Promise<{ providers: ModelProvider[]; ollama_recommendations: OllamaRecommendation[] }> {
  return apiJson("/api/admin/model-providers");
}

export async function createModelProvider(payload: ModelProvider) {
  return apiJson<{ provider: ModelProvider }>(`/api/admin/model-providers/${encodeURIComponent(payload.id)}`, { method: "PUT", json: payload });
}

export async function checkModelProvider(id: string) {
  return apiJson<ModelProviderHealth>(
    `/api/admin/model-providers/${encodeURIComponent(id)}/health`,
    { method: "POST", json: {} },
  );
}

export async function pullOllamaModel(id: string, model: string): Promise<ModelPullJob> {
  return apiJson<ModelPullJob>(`/api/admin/model-providers/${encodeURIComponent(id)}/models/pull`, {
    method: "POST",
    json: { model },
  });
}

export async function getOllamaPullStatus(id: string, jobId: string): Promise<ModelPullJob> {
  return apiJson<ModelPullJob>(`/api/admin/model-providers/${encodeURIComponent(id)}/models/pull/${encodeURIComponent(jobId)}`);
}
