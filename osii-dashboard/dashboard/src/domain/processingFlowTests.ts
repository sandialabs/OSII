export type FlowTestAttempt = {processor?: string; ok: boolean | null; detail?: string; endpoint?: string; diagnostics?: {error?: string; traceback?: string; endpoint?: string; [key: string]: unknown}; [key: string]: unknown};
export type FlowTestStep = FlowTestAttempt & {step?: string; route?: string; extensions?: string[]; attempts?: FlowTestAttempt[]};
export type FlowTestReport = {ok: boolean; tested_at: string; sample?: string; results: FlowTestStep[]; fingerprint?: string};
export function flowTestStatus(report?: FlowTestReport | null): {label: string; color: "success" | "warning" | "error" | "default"} {
  if (!report) return {label: "Not tested", color: "default"};
  if (!report.ok) return {label: "Needs attention", color: "error"};
  if (report.results.some(step => step.attempts?.some(attempt => attempt.ok === false))) return {label: "Ready · fallback used", color: "warning"};
  return {label: "Ready", color: "success"};
}
export function flowTestError(attempt: FlowTestAttempt): string {
  let message = attempt.detail || attempt.diagnostics?.error || (attempt.ok === null ? "No compatible sample was available." : "The test failed. Copy the report for full diagnostics.");
  // SDK failures can wrap another service's JSON diagnostics. Surface its cause
  // here; the untouched report retains the full traceback and Python runtime.
  const start = message.indexOf("{");
  if (start >= 0) {
    try {
      const body = JSON.parse(message.slice(start));
      const detail = body.detail ?? body;
      const cause = typeof detail === "string" ? detail : detail.error ?? detail.diagnostics?.error ?? detail.message;
      if (typeof cause === "string" && cause) message = cause;
    } catch { /* Ordinary provider errors do not have a JSON body. */ }
  }
  return message.length > 600 ? `${message.slice(0, 600)}… Full details are in Copy report.` : message;
}
export function flowStepLabel(step: FlowTestStep): string {
  if (step.step === "synthesize") return "Generate summaries";
  if (step.step === "enrich") return "Enrich documents";
  if (step.step === "embed") return "Build embeddings";
  if (step.step === "extract") {
    const extensions = step.extensions || [];
    if (extensions.includes("*")) return "Read other file types";
    if (extensions.includes(".pdf") && extensions.includes(".txt")) return "Read documents";
    if (extensions.includes(".pdf") && extensions.includes(".png")) return "Read PDFs and images";
    return extensions.length ? `Read files · ${extensions.slice(0, 3).join(", ")}` : "Read files";
  }
  if (step.processor?.toLowerCase().includes("embedding")) return "Build embeddings";
  if (step.processor?.toLowerCase().includes("synthes")) return "Generate summaries";
  return step.processor?.includes("keywords") || step.processor?.includes("enrich") ? "Enrich documents" : "Processor test";
}

/** Put actionable failures first while retaining each check's original number. */
export function flowTestEntries(report: FlowTestReport): {step: FlowTestStep; index: number; attention: boolean}[] {
  const entries = report.results.map((step, index) => ({step, index, attention: step.ok !== true || Boolean(step.attempts?.some(item => item.ok === false))}));
  const priority = (entry: typeof entries[number]) => entry.step.ok !== true ? 0 : entry.attention ? 1 : 2;
  return entries.sort((a, b) => priority(a) - priority(b) || a.index - b.index);
}
