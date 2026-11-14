export type FileDisplay = {
  view: "thumbnails" | "list";
  show_name: boolean;
  show_size: boolean;
  metadata: "none" | "format" | "modified" | "path";
};
export const defaultFileDisplay: FileDisplay = {
  view: "thumbnails",
  show_name: true,
  show_size: false,
  metadata: "none",
};
