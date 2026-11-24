import { HomeOutlined, FolderOutlined, SearchOutlined, ChatOutlined, CollectionsBookmarkOutlined, ArticleOutlined, InsightsOutlined, ScatterPlotOutlined, InsertDriveFileOutlined, DocumentScannerOutlined } from "@mui/icons-material";
import { workbenchNavigation } from "../../domain/workbench";
import type { NavigationItem } from "./WorkbenchLayout";
const icons = { home: HomeOutlined, files: InsertDriveFileOutlined, folder: FolderOutlined, search: SearchOutlined, chat: ChatOutlined, collections: CollectionsBookmarkOutlined, report: ArticleOutlined, insights: InsightsOutlined, topics: ScatterPlotOutlined, ocr: DocumentScannerOutlined };
export const sharedNavigation: readonly (NavigationItem & { path: string })[] = workbenchNavigation.map(item => ({ ...item, icon: icons[item.icon] }));
