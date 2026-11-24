import { apiJson } from "./client";

export type DatabaseSchema = {
  available: boolean; backend: string; detail?: string;
  tables: { name: string; columns: { name: string; type: string }[] }[];
  limits?: { rows: number; columns: number; cell_characters: number; bytes: number; statement_timeout_ms: number };
};
export type DatabaseResult = {
  columns: { key: string; label: string; data_type: "json" }[];
  rows: Record<string, unknown>[]; row_count: number; limited: boolean;
  truncated_cells: number; elapsed_ms: number; read_only: boolean;
};
export const getDatabaseSchema = () => apiJson<DatabaseSchema>("/api/admin/database/schema");
export const queryDatabase = (sql: string, limit: number) => apiJson<DatabaseResult>("/api/admin/database/query", { method: "POST", json: { sql, limit } });
