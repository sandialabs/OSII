import type { LibraryFlow } from "./libraryProducts";

export const READ_WIKIS_PATH = "/tools/wikis";
export const CREATE_WIKI_PATH = "/tools/wiki";

export type ToolAvailability = { enabled: boolean; reason: string };
export type WorkbenchHome = {
  setup: { visible: boolean };
  documents: number;
  text_documents: number;
  indexed_documents: number;
  tools: Record<string, ToolAvailability>;
};

// Data only: consumed by local routing, hosted adapters, tiles, and navigation.
export const ocrWorkbench = {
  id: "ocr", path: "/tools/ocr", label: "OCR Workbench", illustration: "🔠", icon: "ocr",
  description: "Read scanned PDFs or images and correct saved text.",
  scope: "One file",
  input: "source",
  flow: { reads: ["source", "text"], writes: ["text", "artifacts"] },
} as const satisfies DocumentTool;

type DocumentTool = {
  id: string;
  path: string;
  label: string;
  illustration: string;
  icon: string;
  description: string;
  scope: string;
  input: "source" | "library";
  flow: LibraryFlow;
};

export const documentTools = [
  { id: "browse", path: "/browse", label: "Browse", illustration: "📂", icon: "folder", description: "Open files by folder.",
    scope: "Library folders", input: "library", flow: { reads: ["metadata"], writes: [] } },
  { id: "search", path: "/search", label: "Search", illustration: "🔎", icon: "search", description: "Find relevant passages.",
    scope: "Library or collection", input: "library", flow: { reads: ["text", "index"], writes: [] } },
  { id: "chat", path: "/chat", label: "Chat", illustration: "💬", icon: "chat", description: "Ask questions grounded in your documents.",
    scope: "Library, folder, collection, or file", input: "library", flow: { reads: ["text", "index"], writes: [] } },
  { id: "research", path: "/research", label: "Create a Report", illustration: "📝", icon: "report", description: "Draft and export a cited report.",
    scope: "Collection or file", input: "library", flow: { reads: ["text"], writes: [] } },
  { id: "wiki", path: READ_WIKIS_PATH, label: "Wikis", illustration: "📖", icon: "wiki", description: "Read, edit, and create wikis from your documents.",
    scope: "Library, folder, collection, or file", input: "library", flow: { reads: ["text", "artifacts"], writes: ["artifacts"] } },
  { id: "overview", path: "/library-overview", label: "Analyze Library", illustration: "📊", icon: "insights", description: "Review what your library contains.",
    scope: "Library", input: "library", flow: { reads: ["metadata", "artifacts", "index"], writes: [] } },
  { id: "create-collections", path: "/tools/collections", label: "Create Collections", illustration: "🗂️", icon: "collections", description: "Group documents by folder, selection, or topic.",
    scope: "Library", input: "library", flow: { reads: ["metadata", "index"], writes: ["collections"] } },
  { id: "topics", path: "/topics", label: "Explore Topics", illustration: "🗺️", icon: "topics", description: "Explore related documents on a topic map.",
    scope: "Library, folder, or collection", input: "library", flow: { reads: ["index", "metadata"], writes: ["collections"] } },
  ocrWorkbench,
] as const satisfies readonly DocumentTool[];

export const workbenchNavigation = [
  { id: "home", path: "/", label: "Home", group: "home", icon: "home" },
  { id: "files", path: "/files", label: "Files", group: "documents", icon: "files" },
  { ...documentTools[0], group: "documents" },
  { id: "collections", path: "/collections", label: "Collections", group: "documents", icon: "collections" },
  ...documentTools.slice(1).map(tool => ({ ...tool, group: "tools" as const })),
] as const;
