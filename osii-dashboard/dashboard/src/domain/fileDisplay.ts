export type FileDisplay = {
  view: "thumbnails" | "list";
  show_name: boolean;
  name_source: "filename" | "descriptive_title";
  show_size: boolean;
  metadata: "none" | "format" | "modified" | "path";
};
export const defaultFileDisplay: FileDisplay = {
  view: "thumbnails",
  show_name: true,
  name_source: "filename",
  show_size: false,
  metadata: "none",
};
