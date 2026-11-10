import type { ComponentType } from "react";
import type { TopicPoint } from "../types";
import type { SelectionMode } from "./geometry";
export type TopicViewProps = {
  resetPreviewToken?: number;
  points: TopicPoint[];
  selectedId: string;
  relatedIds: ReadonlySet<string>;
  selectedIds?: ReadonlySet<string>;
  onSelect: (id: string) => void;
  onSelection?: (ids: string[], mode: SelectionMode) => void;
  onPreview?: (ids: string[]) => void;
};
export type TopicViewDefinition = {
  id: string;
  label: string;
  View: ComponentType<TopicViewProps>;
};
