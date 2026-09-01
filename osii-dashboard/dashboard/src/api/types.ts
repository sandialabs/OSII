// src/api/types.ts
export type ScopeType = "root" | "folder" | "collection" | "object";
export type SearchMode = "semantic" | "lexical" | "hybrid";

export type RootScopeDescriptor = {
  scope_type: "root";
  scope_id: "root";
  label: string;
};

export type FolderScopeDescriptor = {
  scope_type: "folder";
  scope_id: string;
  folder_id: string;
  path: string;
  label: string;
};

export type CollectionScopeDescriptor = {
  scope_type: "collection";
  scope_id: string;
  collection_id: string;
  label: string;
  kind?: string | null;
  description?: string | null;
  document_count?: number | null;
};

export type ObjectScopeDescriptor = {
  scope_type: "object";
  scope_id: string;
  file_id: string;
  label: string;
};

export type ScopeDescriptor =
  | RootScopeDescriptor
  | FolderScopeDescriptor
  | CollectionScopeDescriptor
  | ObjectScopeDescriptor;

export type ScopeDescribeRequest =
  | { scope_type: "root" }
  | { scope_type: "folder"; folder_id: string }
  | { scope_type: "collection"; collection_id: string }
  | { scope_type: "object"; file_id: string };

export type ScopeMembersResponse = {
  scope: ScopeDescriptor;
  member_file_ids: string[];
};

export type ScopeSummariesRequest = {
  scope: ScopeDescribeRequest;
};

export type FolderScopeListResponse = {
  scopes: FolderScopeDescriptor[];
};

export type CollectionScopeListResponse = {
  scopes: CollectionScopeDescriptor[];
};

export type CollectionReference = {
  id: string;
  name: string;
  kind: string | null;
};

export type ProcessingToolRef = {
  name: string | null;
  display_name: string | null;
};

export type ProcessingCapabilities = {
  supports_markdown_render?: boolean;
} & Record<string, unknown>;

export type ObjectProcessing = {
  extractor: ProcessingToolRef;
  synthesizer: ProcessingToolRef;
  canonical_text_path: string;
  editable_text_path: string | null;
  has_editable_text: boolean;
  capabilities: ProcessingCapabilities;
};

export type ObjectSourceState = {
  file_id: string;
  status: string;
  source_relpath: string | null;
};

export type ObjectSummary = {
  file_id: string;
  filename?: string | null;
  source_relpath?: string | null;
  source_file_relpath?: string | null;
  mime?: string | null;
  size_bytes?: number | null;
  mtime_utc?: string | null;
  collections: CollectionReference[];
  processing: ObjectProcessing;
  source_state?: ObjectSourceState | null;
  has_preferred_text: boolean;
  preferred_text_kind?: string | null;
  has_synthesis: boolean;
  has_enrichments: boolean;
  synthesis_preview?: string | null;
  preview_available: boolean;
};

export type ScopeSummariesResponse = {
  scope: Record<string, unknown>;
  summaries: ObjectSummary[];
};

export type ObjectSummariesRequest = {
  file_ids: string[];
};

export type ObjectSummariesResponse = {
  summaries: ObjectSummary[];
};

export type SourceRescanSummary = {
  unchanged: number;
  changed: number;
  moved: number;
  missing_source: number;
  new_files: number;
};

export type SourceRescanResponse = {
  summary: SourceRescanSummary;
  unchanged: Array<{ source_relpath: string; file_id: string }>;
  changed: Array<{ source_relpath: string; old_file_id: string; new_file_id: string }>;
  moved: Array<{ old_source_relpath: string; new_source_relpath: string; file_id: string }>;
  missing_source: Array<{ source_relpath: string; file_id: string }>;
  new_files: Array<{ source_relpath: string; file_id: string }>;
  applied?: {
    moved_updated: number;
    missing_marked: number;
    changed_marked: number;
    active_marked: number;
    folder_tree_rebuilt: boolean;
  };
};

export type FileMeta = {
  source_relpath: string;
  filename: string;
  mime: string | null;
  size_bytes: number | null;
  mtime_utc: string | null;
};

export type HashMeta = {
  sha256: string;
};

export type ObjectMeta = {
  file: FileMeta;
  hash: HashMeta;
};

export type Span = {
  char_start: number;
  char_end: number;
};

export type SourceOrigin = {
  source_type?: string | null;
  unit_type?: string | null;
  page?: number | null;
} & Record<string, unknown>;

export type ManifestRecord = {
  kind: string;
  id: string;
  path: string;
  type?: string | null;
  span?: Span | null;
  source_origin?: SourceOrigin | null;
  related_ids?: string[];
} & Record<string, unknown>;

export type ObjectOverview = {
  file_id: string;
  meta: ObjectMeta;
  text_count: number;
  image_count: number;
  has_synth: boolean;
  text_items: ManifestRecord[];
  image_items: Array<Record<string, unknown>>;
} & Record<string, unknown>;

export type EnrichmentBundleFileEntry = {
  name: string;
  relpath: string;
  is_dir: boolean;
};

export type EnrichmentListEntryFile = {
  name: string;
  kind: "file";
  relpath: string;
};

export type EnrichmentListEntryBundle = {
  name: string;
  kind: "bundle";
  relpath: string;
  files: EnrichmentBundleFileEntry[];
};

export type EnrichmentListEntry =
  | EnrichmentListEntryFile
  | EnrichmentListEntryBundle;

export type TextRepresentation = {
  name: string;
  kind: string;
  path: string;
  exists: boolean;
  preferred: boolean;
};

export type ExtractionVariant = {
  id: string;
  created_utc: string;
  extractor: { name: string; version: string };
  status: string;
  text_sha256?: string | null;
  text_chars: number;
  manifest_records: number;
  primary: boolean;
  text_path: string;
  manifest_path: string;
  provenance_path: string;
};

export type ExtractionVariantsResponse = {
  file_id: string;
  primary_id: string | null;
  variants: ExtractionVariant[];
};

export type ExtractionArtifact = {
  id: string;
  kind: string;
  media_type: string;
  source_origin: Record<string, unknown>;
  filename: string;
  size_bytes: number | null;
  data: unknown | null;
};

export type ExtractionArtifactsResponse = {
  file_id: string;
  variant_id: string;
  artifacts: ExtractionArtifact[];
};

export type ObjectSynthesisArtifact = {
  name: string;
  text_path: string;
  toml_path: string;
  scope: string;
};

export type ArtifactActionFlags = {
  can_extract: boolean;
  can_synthesize: boolean;
  can_enrich: boolean;
  source_is_active: boolean;
};

export type ObjectArtifacts = {
  has_extraction: boolean;
  has_synthesis: boolean;
  has_enrichments: boolean;
  manifest_record_count: number;
  text_representations: TextRepresentation[];
  syntheses: ObjectSynthesisArtifact[];
  enrichments: EnrichmentListEntry[];
};

export type ObjectArtifactSummary = {
  file_id: string;
  source_state: ObjectSourceState;
  artifacts: ObjectArtifacts;
  actions: ArtifactActionFlags;
};

export type ObjectAggregate = {
  file_id: string;
  meta: ObjectMeta;
  overview: ObjectOverview;
  collections: CollectionReference[];
  processing: ObjectProcessing;
  enrichments: EnrichmentListEntry[];
  artifact_summary: ObjectArtifactSummary;
  governance: {
    sensitivity_labels: string[];
    tags: string[];
    handling_notes: string;
    updated_utc: string | null;
  } | null;
};

export type ObjectTextsResponse = {
  file_id: string;
  representations: TextRepresentation[];
  segments: ManifestRecord[];
};

export type PreferredTextResponse = {
  file_id: string;
  representation: string;
  kind: string;
  text: string;
  path: string;
};

export type ObjectManifestResponse = {
  file_id: string;
  records: ManifestRecord[];
};

export type ObjectSynthesesResponse = {
  file_id: string;
  current_text: string | null;
  current_toml: Record<string, unknown> | null;
  syntheses: {
    name: string;
    text_path: string;
    toml_path: string;
    scope: string;
  }[];
};

export type CollectionResource = {
  id: string;
  name: string;
  description: string | null;
  kind: string | null;
  color: string | null;
  document_count: number;
  created_utc: string;
  updated_utc: string;
};

export type CollectionListResponse = {
  collections: CollectionResource[];
};

export type CollectionEnvelope = {
  collection: CollectionResource;
};

export type CollectionMembersResponse = {
  collection: CollectionResource;
  file_ids: string[];
};

export type CollectionMembersAddRequest = {
  file_ids: string[];
};

export type CollectionMembersAddResponse = {
  collection_id: string;
  added: string[];
  already_present: string[];
};

export type CollectionMemberRemoveResponse = {
  collection_id: string;
  file_id: string;
  removed: boolean;
};

export type CollectionSynthesisArtifact = {
  name: string;
  relpath: string;
};

export type CollectionArtifactSummary = {
  collection_id: string;
  artifacts: {
    member_count: number;
    has_synthesis: boolean;
    has_enrichments: boolean;
    syntheses: CollectionSynthesisArtifact[];
    enrichments: EnrichmentListEntry[];
  };
  actions: {
    can_synthesize: boolean;
    can_enrich: boolean;
  };
};

export type CollectionDetailResponse = {
  collection: CollectionResource;
  artifact_summary: CollectionArtifactSummary;
};

export type CollectionSynthesesResponse = {
  collection: CollectionResource;
  syntheses: CollectionSynthesisArtifact[];
};

export type CanonicalSpanResponse = {
  file_id: string;
  char_start: number;
  char_end: number;
  text: string;
};

export type CanonicalSpanContextResponse = {
  file_id: string;
  char_start: number;
  char_end: number;
  match_text: string;
  before_text: string;
  after_text: string;
  window_start: number;
  window_end: number;
};

export type EnrichmentsListResponse = {
  scope: Record<string, unknown>;
  enrichments: EnrichmentListEntry[];
};

export type ObjectEnrichmentPayloadResponse = {
  file_id?: string;
  scope_type?: ScopeType;
  scope_id?: string;
  filename: string;
  relpath: string;
  data: unknown;
};

export type ProvenanceRef = {
  file_id?: string | null;
  segment_id?: string | null;
  page?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  source_origin?: Record<string, unknown>;
};

export type StandardTableArtifact = {
  artifact_type: "table";
  title: string;
  description?: string | null;
  columns: Array<{
    key: string;
    label: string;
    data_type: "string" | "number" | "integer" | "boolean" | "date" | "datetime" | "json";
    unit?: string | null;
    description?: string | null;
  }>;
  rows: Array<Record<string, unknown>>;
  row_provenance?: ProvenanceRef[][];
};

export type StandardKnowledgeGraphArtifact = {
  artifact_type: "knowledge_graph";
  title: string;
  description?: string | null;
  nodes: Array<{
    id: string;
    label: string;
    entity_type: string;
    properties?: Record<string, unknown>;
    provenance?: ProvenanceRef[];
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    relation: string;
    properties?: Record<string, unknown>;
    provenance?: ProvenanceRef[];
  }>;
};

export type StandardEntityListArtifact = {
  artifact_type: "entity_list";
  title: string;
  description?: string | null;
  entities: Array<{
    id: string;
    name: string;
    entity_type: string;
    aliases?: string[];
    attributes?: Record<string, unknown>;
    mentions?: ProvenanceRef[];
  }>;
};

export type StandardWikiMarkdownArtifact = {
  artifact_type: "wiki_markdown";
  title: string;
  markdown: string;
  citations?: ProvenanceRef[];
};

export type StandardEnrichmentArtifact =
  | StandardTableArtifact
  | StandardKnowledgeGraphArtifact
  | StandardEntityListArtifact
  | StandardWikiMarkdownArtifact;

export type ErrorResponse = {
  error?: string;
  detail?: string | object | unknown[];
} & Record<string, unknown>;

export type QueueBrowseEntry = {
  name: string;
  display: string;
  path: string;
  type: "file" | "folder";
  size_bytes: number | null;
  processed: boolean;
};

export type QueueBrowseResponse = {
  current_path: string;
  display_path: string;
  entries: QueueBrowseEntry[];
};

export type UploadResponse = {
  uploads: Array<{ name: string; path: string; display: string; size_bytes: number; source: "upload" }>;
};

export type IntakePreview = {
  matched_count: number;
  processed_count: number;
  unprocessed_count: number;
  total_size: number;
  total_size_human: string;
  sample: Array<{ path: string; display: string }>;
  extractor_plan: Array<{
    extension: string;
    extractor: string;
    count: number;
    sample: string[];
  }>;
  stopped_reason?: string | null;
  processing_plan?: {
    matched_count: number;
    unique_document_count: number;
    extracted_count: number;
    missing_extraction_count: number;
    blocked_count: number;
    steps: Array<{
      id: "extract" | "synthesize" | "embed" | "enrich";
      label: string;
      eligible_count: number;
      current_count: number;
      scope_note?: string;
    }>;
  };
};

export type CapabilityReadiness = {
  id: string;
  display_name: string;
  kind?: "extractor" | "synthesizer" | "embedder" | "enricher";
  aliases?: string[];
  description?: string;
  available: boolean;
  detail: string;
  bundled: boolean;
  model?: string;
  base_url?: string;
  lexical?: boolean;
  provider?: string;
  dimensions?: number;
  index_compatible?: boolean;
  index_rebuild_required?: boolean;
  indexed_model?: string;
  config_schema?: ProcessorConfigSchema;
  descriptor?: {
    config_schema?: ProcessorConfigSchema;
    [key: string]: unknown;
  } | null;
};

export type ProcessorConfigProperty = {
  type?: "string" | "number" | "integer" | "boolean";
  title?: string;
  description?: string;
  default?: unknown;
  enum?: Array<string | number>;
  minimum?: number;
  maximum?: number;
  format?: string;
};

export type ProcessorConfigSchema = {
  type?: "object";
  properties?: Record<string, ProcessorConfigProperty>;
  required?: string[];
  additionalProperties?: boolean;
};

export type IntakeReadiness = {
  defaults: {
    extractor: string;
    synthesizer: string;
    embedder: string;
    enricher: string;
  };
  extractors: CapabilityReadiness[];
  synthesizers: CapabilityReadiness[];
  embedders: CapabilityReadiness[];
  enrichers: CapabilityReadiness[];
  external: CapabilityReadiness[];
  semantic_indexes?: Array<{
    index_id: string;
    provider_id: string;
    endpoint_type?: string | null;
    model: string;
    model_digest?: string | null;
    dimensions?: number | null;
    normalized: boolean;
    semantic: boolean;
    relpath: string;
    created_utc?: string | null;
    compatible: boolean;
  }>;
};

export type IntakeResolveResponse = {
  queue_items: Array<{
    path: string;
    display: string;
    kind: "file" | "folder";
    source: "shared" | "upload";
  }>;
  resolved_files: Array<{ path: string; display: string }>;
  preview: IntakePreview;
};

export type ProcessingRun = {
  id: string;
  status: "pending" | "queued" | "running" | "done" | "error" | string;
  control_state?: "running" | "pause_requested" | "paused" | "cancel_requested" | "cancelled" | string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  completed?: number;
  total?: number;
  workflow?: "intake" | "library";
  expert_context?: string | null;
  operations?: {
    extract?: boolean;
    extract_mode?: string;
    extraction_policy?: string;
    synthesize?: string | null;
    embed?: boolean;
    chunking?: {
      method: "sentence_window" | "paragraph" | "window";
      chunk_size: number;
      chunk_overlap: number;
    } | null;
    enrich?: string | null;
  };
  indexing_status?: string;
  indexing_error?: string | null;
  items?: Array<{
    display: string;
    status: string;
    error?: string | null;
    extractor?: string | null;
    extraction_variant_id?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    duration_seconds?: number | null;
  }>;
  logs?: string[];
  queue_job_id?: string;
  collection_id?: string | null;
  collection?: CollectionResource | null;
  error?: string | null;
  resolved_count?: number;
  preview?: IntakePreview;
};

export type ProcessorEndpoint = {
  id: string;
  display_name: string;
  kind: "extractor" | "synthesizer" | "embedder" | "enricher";
  base_url: string;
  enabled: boolean;
};

export type ModelProvider = {
  id: string;
  type: "ollama" | "openai";
  base_url: string;
  enabled: boolean;
  priority: number;
  embedding_model: string;
  synthesis_model: string;
  chat_model: string;
  credential_env: string;
  credential_required?: boolean;
  credential_present?: boolean;
  credential_source?: "environment" | "repo_env" | null;
  credential_writable?: boolean;
  implicit?: boolean;
};

export type ManagedCapabilityService = {
  id: string;
  display_name: string;
  description: string;
  status: "running" | "external" | "stopped" | "failed" | string;
  ownership: "osii" | "external" | "none" | string;
  url: string;
  health_path: string;
  can_start: boolean;
  can_stop: boolean;
  can_restart: boolean;
  prerequisite?: string | null;
  detail?: string | null;
};

export type SetupMethod = {
  id: string;
  display_name: string;
  available: boolean;
  description: string;
  model?: string | null;
};

export type SetupSummary = {
  overall_status: "ready" | "ready_optional" | "action_required";
  headline: string;
  extraction_ready: boolean;
  ai_ready: boolean;
  methods: Record<"extractor" | "synthesizer" | "embedder" | "enricher", SetupMethod>;
  providers: ModelProvider[];
  services: ManagedCapabilityService[];
  service_control_available: boolean;
  readiness: IntakeReadiness;
};

export type OllamaModelDetail = {
  name: string;
  size?: number | null;
  digest?: string | null;
  modified_at?: string | null;
  family?: string | null;
  parameter_size?: string | null;
  quantization_level?: string | null;
};

export type OllamaRecommendation = {
  model: string;
  capability: "embedding" | "chat";
  display_name: string;
  publisher: string;
  size_label: string;
  description: string;
};

export type ModelProviderHealth = {
  ok: boolean;
  models: string[];
  model_details: OllamaModelDetail[];
  missing_models: string[];
  pull_commands: string[];
  recommendations: OllamaRecommendation[];
  detail?: string;
};

export type ModelPullJob = {
  job_id: string;
  provider_id: string;
  model: string;
  status: "queued" | "running" | "complete" | "error";
  status_text: string;
  completed: number;
  total: number;
  detail?: string | null;
};

export type EditedTextSegment = {
  id: string;
  text: string;
};

export type EditedTextStaleFlags = {
  embeddings: boolean;
  search_chunks: boolean;
  syntheses?: boolean;
  enrichments?: boolean;
};

export type EditedTextReadResponse = {
  file_id: string;
  exists: boolean;
  representation: "edited";
  segments: EditedTextSegment[];
};

export type EditedTextWriteRequest = {
  segments: EditedTextSegment[];
};

export type EditedTextWriteResponse = {
  file_id: string;
  representation: "edited";
  updated: boolean;
  segments: EditedTextSegment[];
  stale: EditedTextStaleFlags;
};

export type EditedTextDeleteResponse = {
  file_id: string;
  representation: "edited";
  removed: boolean;
  stale: EditedTextStaleFlags;
};

export type EnrichmentJobResponse = {
  run_id: string;
  status: string;
  scope: Record<string, unknown>;
  enricher_name: string;
};

export type ScopeArtifactsRequest = {
  scope: ScopeDescribeRequest;
};

export type ScopeSynthesisArtifact = {
  name: string;
  relpath: string;
};

export type ScopeArtifactSummary = {
  member_count: number;
  has_synthesis: boolean;
  synthesis_preview: string | null;
  syntheses: ScopeSynthesisArtifact[];
  has_enrichments: boolean;
  enrichments: EnrichmentListEntry[];
};

export type ScopeArtifactActions = {
  can_synthesize: boolean;
  can_enrich: boolean;
};

export type ScopeArtifactsResponse = {
  scope: ScopeDescriptor;
  artifact_summary: ScopeArtifactSummary;
  actions: ScopeArtifactActions;
};

export type ChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

export type ChatCitation = {
  file_id: string;
  filename: string | null;
  source_relpath: string | null;
  snippet: string | null;
  chunk_id: string | null;
  segment_id: string | null;
  page: number | null;
  char_start: number | null;
  char_end: number | null;
  source_origin: {
    grounding_type: string;
    char_start: number;
    char_end: number;
    segment_ids?: string[];
    pages?: number[];
    overlap_with_previous?: number;
  } | null;
};

export type ChatRequest = {
  query: string;
  scope: ScopeDescribeRequest;
  history: ChatMessage[];
};

export type ChatResponse = {
  answer: string;
  citations: ChatCitation[];
  provider: string;
  fallback_used: boolean;
  retrieval_mode: string;
};

export type SearchGroupBy = "file";

export type SearchRequest = {
  query: string;
  mode?: SearchMode;
  top_k?: number;
  scope: ScopeDescribeRequest;
  group_by?: SearchGroupBy;
};

export type SearchResultSourceOrigin = {
  grounding_type: string;
  char_start: number;
  char_end: number;
} & Record<string, unknown>;

export type SearchScopedResult = {
  file_id: string;
  filename: string | null;
  source_relpath: string | null;
  snippet: string | null;
  score: number;
  match_type: string | null;
  chunk_id: string | null;
  segment_id: string | null;
  chunk_method: string | null;
  chunk_index: number | null;
  page: number | null;
  char_start: number | null;
  char_end: number | null;
  source_text_representation: string | null;
  source_text_kind: string | null;
  source_origin: SearchResultSourceOrigin | null;
  collections: CollectionReference[];
} & Record<string, unknown>;

export type SearchScopedResponse = {
  query: string;
  mode: SearchMode;
  retrieval_mode_used: SearchMode;
  top_k: number;
  scope: Record<string, unknown>;
  group_by: SearchGroupBy;
  results: SearchScopedResult[];
};
