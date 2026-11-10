import { apiJson } from "./client";
import type { ReportFormat, ReportScope, ReportSource, ResearchReport } from "../domain/research";

export function writeResearchReport(payload: {
  scope: ReportScope; prompt: string; format: ReportFormat;
  current_markdown?: string; improvement?: string; sources?: ReportSource[];
}): Promise<ResearchReport> {
  return apiJson<ResearchReport>("/api/research/report", { method: "POST", json: payload });
}
