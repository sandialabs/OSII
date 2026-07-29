// src/api/jobs.ts
import { apiJson } from "./client";
import type {
  EnrichmentJobResponse,
  ScopeDescribeRequest,
} from "./types";

export type ObjectSynthesisRequest = {
  synthesizer_name: string;
  expert_context?: string | null;
  synthesizer_config?: Record<string, unknown>;
};

export type ObjectSynthesisJobResponse = {
  run_id: string;
  status: string;
  file_id: string;
  synthesizer_name: string;
};

export async function runObjectSynthesis(
  fileId: string,
  payload: ObjectSynthesisRequest,
): Promise<ObjectSynthesisJobResponse> {
  return apiJson<ObjectSynthesisJobResponse>(
    `/api/synthesis/objects/${encodeURIComponent(fileId)}`,
    {
      method: "POST",
      json: payload,
    },
  );
}

export async function runEnrichmentJob(payload: {
  enricher_name: string;
  scope: ScopeDescribeRequest;
  enricher_config?: Record<string, unknown>;
}): Promise<EnrichmentJobResponse> {
  return apiJson<EnrichmentJobResponse>("/api/enrichment-jobs/run", {
    method: "POST",
    json: payload,
  });
}