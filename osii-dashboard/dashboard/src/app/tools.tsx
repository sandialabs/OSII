import { lazy, type ComponentType } from "react";
import MoveToInboxOutlined from "@mui/icons-material/MoveToInboxOutlined";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import FolderOutlined from "@mui/icons-material/FolderOutlined";
import BuildOutlined from "@mui/icons-material/BuildOutlined";
import { sharedNavigation } from "./layout/workbenchNavigation";
import type { NavigationItem } from "./layout/WorkbenchLayout";
export type WorkbenchTool = NavigationItem & { path: string; Page: ComponentType; navigation?: boolean };
const pages: Record<string, ComponentType> = {
  home: lazy(() => import("../features/home/pages/HomePage").then(m => ({ default: m.HomePage }))),
  files: lazy(() => import("../features/home/pages/FilesPage").then(m => ({ default: m.FilesPage }))),
  browse: lazy(() => import("../features/browse/pages/BrowsePage").then(m => ({ default: m.BrowsePage }))),
  search: lazy(() => import("../features/search/pages/SearchPage").then(m => ({ default: m.SearchPage }))),
  chat: lazy(() => import("../features/chat/pages/ChatPage").then(m => ({ default: m.ChatPage }))),
  collections: lazy(() => import("../features/collections/pages/CollectionsPage").then(m => ({ default: m.CollectionsPage }))),
  research: lazy(() => import("../features/research/ResearchPage").then(m => ({ default: m.ResearchPage }))),
  overview: lazy(() => import("../features/library/pages/LibraryOverviewPage").then(m => ({ default: m.LibraryOverviewPage }))),
  topics: lazy(() => import("../features/topics/pages/TopicExplorerPage").then(m => ({ default: m.TopicExplorerPage }))),
};
export const workbenchTools: readonly WorkbenchTool[] = [
  ...sharedNavigation.map(item => ({ ...item, Page: pages[item.id] })),
  { id: "intake", path: "/intake", label: "Add files", group: "start", icon: MoveToInboxOutlined,
    Page: lazy(() => import("../features/queue/pages/QueuePage").then(m => ({ default: m.QueuePage }))) },
  { id: "inventory", path: "/inventory", label: "Scan inventory", group: "start", icon: FolderOutlined,
    Page: lazy(() => import("../features/volume/VolumePage")) },
  { id: "setup", path: "/admin/processors", label: "Setup", group: "setup", icon: SettingsOutlined,
    Page: lazy(() => import("../features/admin/pages/ProcessorsPage").then(m => ({ default: m.ProcessorsPage }))) },
  { id: "tool-workbench", path: "/tools/workbench", label: "Processing workbench", group: "tools", icon: BuildOutlined, navigation: false,
    Page: lazy(() => import("../features/files/pages/ToolsPage").then(m => ({ default: m.ToolsWorkbench }))) },
  { id: "tools", path: "/tools", label: "Toolbox", group: "tools", icon: BuildOutlined, navigation: false,
    Page: lazy(() => import("../features/files/pages/ToolsPage").then(m => ({ default: m.ToolsPage }))) },
];
