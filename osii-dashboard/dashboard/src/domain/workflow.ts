import type { IntakeReadiness, ScopeOverview } from "../api/types";

export type WorkflowStepId =
  | "source"
  | "extractor"
  | "embedding"
  | "language"
  | "text"
  | "index";
export type WorkflowStep = {
  id: WorkflowStepId;
  label: string;
  complete: boolean;
  detail: string;
  action: string;
};

export function libraryWorkflowSteps(
  readiness?: IntakeReadiness,
  overview?: ScopeOverview,
  sourceReady?: boolean,
): WorkflowStep[] {
  const extractor = readiness?.extractors.find(
    (item) =>
      item.id === readiness.defaults.extractor ||
      item.aliases?.includes(readiness.defaults.extractor),
  );
  const embedding = readiness?.embedders.find(
    (item) => item.id === readiness.defaults.embedder,
  );
  const count = overview?.file_count ?? 0;
  const textCount = overview?.processing.text_count ?? 0;
  const indexedCount = overview?.processing.indexed_count ?? 0;
  return [
    {
      id: "source",
      label: "Source folder",
      complete: sourceReady ?? Boolean(readiness?.source?.ready_for_intake),
      detail:
        readiness?.source?.detail ||
        "Choose an accessible documents folder and a writable OSII data directory.",
      action: "Choose folder",
    },
    {
      id: "extractor",
      label: "Document reader",
      complete: Boolean(extractor?.available),
      detail: extractor?.available
        ? `${extractor.display_name} is available. Intake also checks the rules for each file type.`
        : "Connect the selected extractor, or choose an available one in the extraction rules.",
      action: "Review extractors",
    },
    {
      id: "embedding",
      label: "Embedding model",
      complete: Boolean(
        embedding?.available &&
          !embedding.lexical &&
          embedding.id !== "local.hashing",
      ),
      detail:
        embedding?.detail ||
        "Select a default embedding model and validate that it returns vectors. A language model alone does not enable semantic search.",
      action: "Set up embeddings",
    },
    {
      id: "language",
      label: "Language model",
      complete: Boolean(readiness?.language_model?.available),
      detail:
        readiness?.language_model?.detail ||
        "Choose a default language model for AI chat. Source excerpts are a no-AI fallback, not generated answers.",
      action: "Set up AI chat",
    },
    {
      id: "text",
      label: "Documents read",
      complete: count > 0 && textCount === count,
      detail: count
        ? `${textCount} of ${count} library documents have saved text. Review failed or empty extractions in Intake.`
        : "Choose files in Intake and run document reading. A connected model does not process files automatically.",
      action: "Read documents",
    },
    {
      id: "index",
      label: "Semantic index",
      complete:
        count > 0 &&
        indexedCount === count &&
        overview?.processing.semantic_index.status === "ready" &&
        (!embedding?.dimensions ||
          embedding.dimensions ===
            overview?.processing.semantic_index.dimensions),
      detail: count
        ? `${indexedCount} of ${count} library documents have current vectors for the selected model. ${overview?.processing.semantic_index.detail ?? ""}`
        : "Build embeddings after reading documents. Changing the embedding model requires a matching index.",
      action: "Build semantic index",
    },
  ];
}
