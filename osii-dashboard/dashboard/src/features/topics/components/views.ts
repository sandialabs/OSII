import { EmbeddingMap } from "./DocumentEmbeddingMap";
import type { TopicViewDefinition } from "./viewTypes";
export const topicViews: readonly TopicViewDefinition[] = [
  { id: "embedding-map", label: "Embedding map", View: EmbeddingMap },
];
