import type { SourceTypes } from "../domain/fileCompatibility";
import { apiJson } from "./client";
import type { ProcessorConfigSchema, ScopeDescribeRequest } from "./types";

export type ToolMethod = {
  execution: "scope" | "intake";
  id: string; action: string; label: string; version: string;
  scopes: string[]; inputs: string[]; outputs: string[];
  source_types?: SourceTypes;
  config_schema: ProcessorConfigSchema;
  model_requirements: Record<string, "required" | "optional">;
  bindings: Record<string, string>; configuration_error: string | null;
  batching?: { whole_scope: boolean; documents: number; characters: number; reduction: string };
  limits: { documents: number; characters: number }; resume: string;
};
export type ToolCatalog = {
  library_id: string;
  permissions?: { run: boolean; edit: boolean };
  methods: ToolMethod[];
  models: { id: string; label: string; capabilities: string[] }[];
  defaults: Record<string, string>;
};
export const getToolCatalog = () => apiJson<ToolCatalog>("/api/enrichment-jobs/tools");

export type ProductRevision = {
  id: string; parent?: string; origin: string; created_at: string | null;
  data: { artifact_type: string; title: string; markdown: string; [key: string]: unknown };
  grounding_needs_review?: boolean;
  provenance: { run_id?: string; inputs?: { file_id: string; filename?: string; has_text?: boolean; truncated?: boolean }[]; [key: string]: unknown };
};
export type ProductHistory = { permissions?: { edit: boolean }; library_id: string; input_state?: string; current: string; data: ProductRevision["data"]; reading_markdown?: string; revisions: ProductRevision[] };
export const getProductHistory = (scope: ScopeDescribeRequest, filename: string) =>
  apiJson<ProductHistory>("/api/enrichments/revisions", { method: "POST", json: { scope, filename } });
export const saveProduct = (scope: ScopeDescribeRequest, filename: string, expected_revision: string, change: { markdown: string } | { revision: string }) =>
  apiJson<ProductHistory>("/api/enrichments/revisions", { method: "PUT", json: { scope, filename, expected_revision, ...change } });


export type SavedProduct = {
  family: string;
  filename: string;
  title: string;
  artifact_type?: string | null;
};

export const listProducts = (scope: ScopeDescribeRequest) =>
  apiJson<{ products: SavedProduct[] }>("/api/products/list", { method: "POST", json: scope });
