export type ToolAvailability = { enabled: boolean; reason: string };
export type WorkbenchHome = {
  setup: { visible: boolean };
  documents: number;
  text_documents: number;
  indexed_documents: number;
  tools: Record<string, ToolAvailability>;
};

// Data only: consumed by local routing, hosted adapters, tiles, and navigation.
export const documentTools = [
  { id: "browse", path: "/browse", label: "Browse", illustration: "📂", icon: "folder", description: "Find documents in their folders and collections." },
  { id: "search", path: "/search", label: "Search", illustration: "🔎", icon: "search", description: "Find words, phrases, and relevant passages." },
  { id: "chat", path: "/chat", label: "Chat", illustration: "💬", icon: "chat", description: "Ask questions grounded in your documents." },
  { id: "research", path: "/research", label: "Create a Report", illustration: "📝", icon: "report", description: "Write and refine a report with cited sources." },
  { id: "overview", path: "/library-overview", label: "Analyze Library", illustration: "📊", icon: "insights", description: "See document counts, processing progress, and saved insights." },
  { id: "topics", path: "/topics", label: "Explore Topics", illustration: "🗺️", icon: "topics", description: "Explore related documents and clusters on a topic map." },
] as const;

export const workbenchNavigation = [
  { id: "home", path: "/", label: "Home", group: "home", icon: "home" },
  { id: "files", path: "/files", label: "Files", group: "documents", icon: "files" },
  { ...documentTools[0], group: "documents" },
  { id: "collections", path: "/collections", label: "Collections", group: "documents", icon: "collections" },
  ...documentTools.slice(1).map(tool => ({ ...tool, group: "tools" as const })),
] as const;
