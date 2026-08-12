import { apiJson } from "./client";

export type ObjectGovernance = {
  sensitivity_labels: string[];
  tags: string[];
  handling_notes: string;
  updated_utc: string | null;
};

export function getObjectGovernance(fileId: string) {
  return apiJson<{ file_id: string; governance: ObjectGovernance }>(
    `/api/objects/${encodeURIComponent(fileId)}/governance`,
  );
}

export function saveObjectGovernance(fileId: string, governance: Omit<ObjectGovernance, "updated_utc">) {
  return apiJson<{ file_id: string; governance: ObjectGovernance }>(
    `/api/objects/${encodeURIComponent(fileId)}/governance`,
    { method: "PUT", json: governance },
  );
}
