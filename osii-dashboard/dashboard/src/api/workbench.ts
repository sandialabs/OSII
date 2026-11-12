import { apiJson } from "./client";
import type { WorkbenchHome } from "../domain/workbench";
export const getWorkbenchHome = () => apiJson<WorkbenchHome>("/api/workbench/home");
export const dismissHomeSetup = () => apiJson("/api/admin/setup/dismiss", { method: "POST", json: {} });
