import { lazy, type ComponentType } from "react";
import HomeOutlined from "@mui/icons-material/HomeOutlined";
import FolderOutlined from "@mui/icons-material/FolderOutlined";
import SearchOutlined from "@mui/icons-material/SearchOutlined";
import ChatOutlined from "@mui/icons-material/ChatOutlined";
import CollectionsBookmarkOutlined from "@mui/icons-material/CollectionsBookmarkOutlined";
import MoveToInboxOutlined from "@mui/icons-material/MoveToInboxOutlined";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import ScatterPlotOutlined from "@mui/icons-material/ScatterPlotOutlined";
import BuildOutlined from "@mui/icons-material/BuildOutlined";
import InsightsOutlined from "@mui/icons-material/InsightsOutlined";

export type WorkbenchTool = {
  id: string;
  path: string;
  label: string;
  description?: string;
  group: "start" | "documents" | "tools" | "setup";
  icon: typeof HomeOutlined;
  Page: ComponentType;
};

// One registration drives routing and navigation; feature pages stay independent.
export const workbenchTools: readonly WorkbenchTool[] = [
  { id: "research", path: "/research", label: "Research reports", group: "tools", icon: InsightsOutlined,
    Page: lazy(() => import("../features/research/ResearchPage").then(m => ({ default: m.ResearchPage }))) },
  { id: "tools", path: "/tools", label: "All tools", group: "tools", icon: BuildOutlined,
    Page: lazy(() => import("../features/files/pages/ToolsPage").then(m => ({ default: m.ToolsPage }))) },
  { id: "intake", path: "/intake", label: "Add files", group: "start", icon: MoveToInboxOutlined,
    Page: lazy(() => import("../features/queue/pages/QueuePage").then(m => ({ default: m.QueuePage }))) },
  { id: "inventory", path: "/inventory", label: "Scan inventory", group: "tools", icon: FolderOutlined,
    Page: lazy(() => import("../features/volume/VolumePage")) },
  { id: "setup", path: "/admin/processors", label: "Setup", group: "setup", icon: SettingsOutlined,
    Page: lazy(() => import("../features/admin/pages/ProcessorsPage").then(m => ({ default: m.ProcessorsPage }))) },
  { id: "files", path: "/", label: "Files", group: "documents", icon: HomeOutlined,
    Page: lazy(() => import("../features/home/pages/HomePage").then(m => ({ default: m.HomePage }))) },
  { id: "library-overview", path: "/library-overview", label: "Library at a glance", group: "tools", icon: InsightsOutlined,
    Page: lazy(() => import("../features/library/pages/LibraryOverviewPage").then(m => ({ default: m.LibraryOverviewPage }))) },
  { id: "browse", path: "/browse", label: "Browse", group: "documents", icon: FolderOutlined,
    Page: lazy(() => import("../features/browse/pages/BrowsePage").then(m => ({ default: m.BrowsePage }))) },
  { id: "search", path: "/search", label: "Search", group: "documents", icon: SearchOutlined,
    Page: lazy(() => import("../features/search/pages/SearchPage").then(m => ({ default: m.SearchPage }))) },
  { id: "topics", path: "/topics", label: "Topic explorer", group: "tools", icon: ScatterPlotOutlined,
    Page: lazy(() => import("../features/topics/pages/TopicExplorerPage").then(m => ({ default: m.TopicExplorerPage }))) },
  { id: "chat", path: "/chat", label: "Chat", group: "documents", icon: ChatOutlined,
    Page: lazy(() => import("../features/chat/pages/ChatPage").then(m => ({ default: m.ChatPage }))) },
  { id: "collections", path: "/collections", label: "Collections", group: "documents", icon: CollectionsBookmarkOutlined,
    Page: lazy(() => import("../features/collections/pages/CollectionsPage").then(m => ({ default: m.CollectionsPage }))) },
];
