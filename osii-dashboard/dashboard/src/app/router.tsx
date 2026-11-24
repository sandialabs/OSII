// src/app/router.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import { Box } from "@mui/material";
import { lazy } from "react";

import { AppLayout } from "./layout/AppLayout";
import { workbenchTools } from "./tools";
import { ToolBoundary } from "./ToolBoundary";
import { PageBreadcrumbs } from "../components/workbench/PageBreadcrumbs";

const CollectionPage = lazy(() => import("../features/collections/pages/CollectionPage").then(m => ({ default: m.CollectionPage })));
const CollectionWikisPage = lazy(() => import("../features/collections/pages/CollectionWikisPage").then(m => ({ default: m.CollectionWikisPage })));
const ProcessorDetailsPage = lazy(() => import("../features/admin/pages/ProcessorDetailsPage").then(m => ({ default: m.ProcessorDetailsPage })));
const FilePage = lazy(() => import("../features/files/pages/FilePage").then(m => ({ default: m.FilePage })));

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
                <Box sx={{ mb: 1.5 }}><PageBreadcrumbs parents={[{ label: "Toolbox", to: "/tools" }]} current={label} /></Box>
              )}
              <Page />
            </ToolBoundary>
          } />
        ))}
        <Route path="/collections/:collectionId" element={<ToolBoundary key="collection"><CollectionPage /></ToolBoundary>} />
        <Route path="/collections/:collectionId/wikis" element={<ToolBoundary key="collection-wikis"><CollectionWikisPage /></ToolBoundary>} />
        <Route path="/files/:fileId" element={<ToolBoundary key="file"><FilePage /></ToolBoundary>} />
        <Route path="/admin/processors/:processorId" element={<ToolBoundary key="processor"><ProcessorDetailsPage /></ToolBoundary>} />
        <Route path="/admin/processors/registered/:registrationId" element={<ToolBoundary key="processor-registration"><ProcessorDetailsPage /></ToolBoundary>} />
        <Route path="/queue" element={<Navigate to="/intake" replace />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
