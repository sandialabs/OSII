export type TopicDocument = { file_id: string; filename: string; document_title?: string | null; title_method?: string | null; source_relpath: string; chunk_count: number };
export type TopicPoint = TopicDocument & { x: number; y: number };
export type TopicIndex = { id: string; provider: string; model: string; dimensions: number; semantic: boolean; created_utc: string | null };
export type TopicMap = {
  index: TopicIndex; scope_count: number; indexed_count: number; stale_count: number;
  unindexed_count: number; shown_count: number; projection: "pca"; explained_variance: number;
  points: TopicPoint[];
};
export type RelatedDocuments = { index: TopicIndex; document: TopicDocument; results: (TopicDocument & { similarity: number })[] };

