import type { ProcessingRun } from "../api/types";

export type RunFile = NonNullable<ProcessingRun["items"]>[number];

export function runTitle(run: ProcessingRun): string {
  return run.processing_flow?.name || run.tool_label || (run.workflow === "tool" ? "Tool run" : "File processing");
}

export function failedRunFiles(run: ProcessingRun): RunFile[] {
  return (run.items ?? []).filter(item => item.error || item.status === "error" || item.status === "partial");
}

export function runHasFailures(run: ProcessingRun): boolean {
  return Boolean(run.error || run.indexing_error || run.status === "error" || run.indexing_status === "error"
    || failedRunFiles(run).length || Object.keys(run.indexing_progress?.failures ?? {}).length);
}

const statusLabels: Record<string, string> = {
  done: "Completed", error: "Failed", partial: "Completed with issues",
  pending: "Pending", staged: "Staged", queued: "Queued", running: "Running", skipped: "Skipped",
  pausing: "Pausing", paused: "Paused", cancelling: "Cancelling", cancelled: "Cancelled", reused: "Reused",
};

export function processingStatus(status: string): string {
  return statusLabels[status] ?? status;
}

export function runStatusLabel(run: ProcessingRun): string {
  return run.status === "done" && runHasFailures(run) ? "Completed with issues" : processingStatus(run.status);
}

export function runReport(run: ProcessingRun, logs = run.logs) {
  return {
    run_id: run.id, queue_job_id: run.queue_job_id, status: run.status, control_state: run.control_state,
    workflow: run.workflow, tool: run.tool_id, title: runTitle(run), scope: run.scope, collection_id: run.collection_id,
    created_at: run.created_at, started_at: run.started_at, finished_at: run.finished_at,
    processing_flow: run.processing_flow, selection: run.selection, operations: run.operations,
    models: run.model_targets, embedding: run.embedding_target, embedding_model: run.embedding_model,
    indexing_file_ids: run.indexing_file_ids, indexing_status: run.indexing_status, indexing_progress: run.indexing_progress,
    error: run.error, error_phase: run.error_phase, indexing_error: run.indexing_error,
    input_summary: run.input_summary, batch_progress: run.batch_progress, diagnostics: run.diagnostics, items: run.items, logs,
  };
}

export function recordedFileStages(run: ProcessingRun, item: RunFile, indexingFiles: ReadonlySet<string>) {
  const diagnostics = item.error ? item.diagnostics ?? [] : [];
  const extractionFailed = item.extract_error || (item.status === "error" && diagnostics.some(record => record.phase === "extraction"));
  const steps: Record<string, string | undefined> = item.steps ?? {
    extraction: extractionFailed ? "error" : item.extraction_variant_id ? "done" : undefined,
    synthesizer: item.synthesis_error ? "error" : item.synthesis ? "done" : undefined,
    enricher: item.enrichment_error ? "error" : item.enrichment ? "done" : undefined,
  };
  const indexFailure = item.file_id ? run.indexing_progress?.failures?.[item.file_id] : undefined;
  const embedding = indexFailure ? "error"
    : run.indexing_status === "done" && item.file_id && indexingFiles.has(item.file_id) ? "done" : undefined;
  const stages = [
    { label: "Check source", processor: "Core file reader", status: steps.source === "error" ? "error" : undefined },
    { label: "Read text", processor: item.extractor, status: steps.extraction },
    { label: "Summarize", processor: item.synthesizer, status: steps.synthesizer },
    { label: "Enrich", processor: item.enricher, status: steps.enricher },
    { label: "Embed", processor: item.embedder ?? run.embedding_target?.provider, status: steps.embedding ?? embedding },
  ];
  return stages.flatMap(({ label, processor, status }) => status ? [{ label, processor, status }] : []);
}
