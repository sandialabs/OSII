// src/app/router.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import { Box } from "@mui/material";
import { lazy } from "react";

import { AppLayout } from "./layout/AppLayout";
import { workbenchTools } from "./tools";
import { ToolBoundary } from "./ToolBoundary";
import { PageBreadcrumbs } from "../components/workbench/PageBreadcrumbs";
import { READ_WIKIS_PATH } from "../utils/routes";

const toolbox = { label: "Toolbox", to: "/tools" };

const CollectionPage = lazy(() => import("../features/collections/pages/CollectionPage").then(m => ({ default: m.CollectionPage })));
const CollectionWikisPage = lazy(() => import("../features/collections/pages/CollectionWikisPage").then(m => ({ default: m.CollectionWikisPage })));
const ProcessorDetailsPage = lazy(() => import("../features/admin/pages/ProcessorDetailsPage").then(m => ({ default: m.ProcessorDetailsPage })));
const RunDetailsPage = lazy(() => import("../features/queue/pages/RunDetailsPage").then(m => ({ default: m.RunDetailsPage })));
const AdvancedQueuePage = lazy(() => import("../features/queue/pages/QueuePage").then(m => ({ default: m.AdvancedQueuePage })));
const FilePage = lazy(() => import("../features/files/pages/FilePage").then(m => ({ default: m.FilePage })));
const ScopeProcessorPage = lazy(() => import("../features/files/pages/ProcessPages").then(m => ({ default: m.ScopeProcessorPage })));

function NotFoundPage() {
  return <Navigate to="/" replace />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        {workbenchTools.map(({ id, path, label, group, Page }) => path === "/" ? (
          <Route key={id} index element={<ToolBoundary key={id}><Page /></ToolBoundary>} />
        ) : (
          <Route key={id} path={path} element={
            <ToolBoundary key={id}>
              {group === "tools" && id !== "tools" && (
                <Box sx={{ mb: 1.5 }}><PageBreadcrumbs
                  parents={id === "create-wiki" ? [toolbox, { label: "Wikis", to: READ_WIKIS_PATH }] : [toolbox]}
                  current={label} /></Box>
              )}
              <Page />
            </ToolBoundary>
          } />
        ))}
        <Route path="/collections/:collectionId" element={<ToolBoundary key="collection"><CollectionPage /></ToolBoundary>} />
        <Route path="/collections/:collectionId/wikis" element={<ToolBoundary key="collection-wikis"><CollectionWikisPage /></ToolBoundary>} />
        <Route path="/files/:fileId" element={<ToolBoundary key="file"><FilePage /></ToolBoundary>} />
        <Route path="/tools/workbench" element={<Navigate to="/tools" replace />} />
        <Route path="/tools/process/:methodId" element={<ToolBoundary key="scope-processor"><ScopeProcessorPage /></ToolBoundary>} />
        <Route path="/admin/processors/:processorId" element={<ToolBoundary key="processor"><ProcessorDetailsPage /></ToolBoundary>} />
        <Route path="/admin/processors/registered/:registrationId" element={<ToolBoundary key="processor-registration"><ProcessorDetailsPage /></ToolBoundary>} />
        <Route path="/intake/advanced" element={<ToolBoundary key="advanced-intake"><AdvancedQueuePage /></ToolBoundary>} />
        <Route path="/intake/runs/:runId" element={<ToolBoundary key="run"><RunDetailsPage /></ToolBoundary>} />
        <Route path="/queue" element={<Navigate to="/intake" replace />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
