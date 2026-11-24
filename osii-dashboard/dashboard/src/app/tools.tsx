import { lazy, type ComponentType } from "react";
import MoveToInboxOutlined from "@mui/icons-material/MoveToInboxOutlined";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import BuildOutlined from "@mui/icons-material/BuildOutlined";
import ManageSearchOutlined from "@mui/icons-material/ManageSearchOutlined";
import { READ_FILES_PATH, SEARCH_INDEX_PATH, SUGGEST_METADATA_PATH, SUMMARIZE_FILE_PATH } from "../utils/routes";
import { sharedNavigation } from "./layout/workbenchNavigation";
import type { NavigationItem } from "./layout/WorkbenchLayout";
export type WorkbenchTool = NavigationItem & { path: string; Page: ComponentType; navigation?: boolean };
const pages: Record<string, ComponentType> = {
  home: lazy(() => import("../features/home/pages/HomePage").then(m => ({ default: m.HomePage }))),
  files: lazy(() => import("../features/home/pages/FilesPage").then(m => ({ default: m.FilesPage }))),
  browse: lazy(() => import("../features/browse/pages/BrowsePage").then(m => ({ default: m.BrowsePage }))),
  search: lazy(() => import("../features/search/pages/SearchPage").then(m => ({ default: m.SearchPage }))),
  chat: lazy(() => import("../features/chat/pages/ChatPage").then(m => ({ default: m.ChatPage }))),
  "create-collections": lazy(() => import("../features/collections/pages/CreateCollectionsPage").then(m => ({ default: m.CreateCollectionsPage }))),
  collections: lazy(() => import("../features/collections/pages/CollectionsPage").then(m => ({ default: m.CollectionsPage }))),
  research: lazy(() => import("../features/research/ResearchPage").then(m => ({ default: m.ResearchPage }))),
  wiki: lazy(() => import("../features/files/pages/ProcessPages").then(m => ({ default: m.CreateWikiPage }))),
  overview: lazy(() => import("../features/library/pages/LibraryOverviewPage").then(m => ({ default: m.LibraryOverviewPage }))),
  ocr: lazy(() => import("../features/ocr/OcrWorkbenchPage").then(m => ({ default: m.OcrWorkbenchPage }))),
  topics: lazy(() => import("../features/topics/pages/TopicExplorerPage").then(m => ({ default: m.TopicExplorerPage }))),
};
export const workbenchTools: readonly WorkbenchTool[] = [
  ...sharedNavigation.map(item => ({ ...item, Page: pages[item.id] })),
  { id: "intake", path: "/intake", label: "Intake & Setup", group: "start", icon: MoveToInboxOutlined,
    Page: lazy(() => import("../features/queue/pages/QueuePage").then(m => ({ default: m.QueuePage }))) },
  { id: "setup", path: "/admin/processors", label: "Advanced setup", group: "setup", icon: SettingsOutlined, navigation: false,
    Page: lazy(() => import("../features/admin/pages/ProcessorsPage").then(m => ({ default: m.ProcessorsPage }))) },
  { id: "tools", path: "/tools", label: "Toolbox", group: "tools", icon: BuildOutlined,
    Page: lazy(() => import("../features/files/pages/ToolsPage").then(m => ({ default: m.ToolsPage }))) },
  { id: "read-files", path: READ_FILES_PATH, label: "Read files", group: "tools", icon: BuildOutlined, navigation: false,
    Page: lazy(() => import("../features/files/pages/ProcessPages").then(m => ({ default: m.ReadFilesPage }))) },
  { id: "summarize-file", path: SUMMARIZE_FILE_PATH, label: "Create a summary", group: "tools", icon: BuildOutlined, navigation: false,
    Page: lazy(() => import("../features/files/pages/ProcessPages").then(m => ({ default: m.SummarizeFilePage }))) },
  { id: "suggest-metadata", path: SUGGEST_METADATA_PATH, label: "Suggest metadata", group: "tools", icon: BuildOutlined, navigation: false,
    Page: lazy(() => import("../features/files/pages/ProcessPages").then(m => ({ default: m.SuggestMetadataPage }))) },
  { id: "search-index", path: SEARCH_INDEX_PATH, label: "Search index", group: "tools", icon: ManageSearchOutlined, navigation: false,
    Page: lazy(() => import("../features/library/pages/SearchIndexPage").then(m => ({ default: m.SearchIndexPage }))) },
  { id: "database", path: "/admin/database", label: "Database explorer", group: "tools", icon: BuildOutlined, navigation: false,
    Page: lazy(() => import("../features/admin/pages/DatabaseExplorerPage").then(m => ({ default: m.DatabaseExplorerPage }))) },
];
