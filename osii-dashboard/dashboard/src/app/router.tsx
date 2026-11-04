// src/app/router.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import { lazy } from "react";

import { AppLayout } from "./layout/AppLayout";
import { workbenchTools } from "./tools";
import { ToolBoundary } from "./ToolBoundary";

const CollectionPage = lazy(() => import("../features/collections/pages/CollectionPage").then(m => ({ default: m.CollectionPage })));
const FilePage = lazy(() => import("../features/files/pages/FilePage").then(m => ({ default: m.FilePage })));

function NotFoundPage() {
  return <Navigate to="/" replace />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        {workbenchTools.map(({ id, path, Page }) => path === "/" ? (
          <Route key={id} index element={<ToolBoundary key={id}><Page /></ToolBoundary>} />
        ) : (
          <Route key={id} path={path} element={<ToolBoundary key={id}><Page /></ToolBoundary>} />
        ))}
        <Route path="/collections/:collectionId" element={<ToolBoundary key="collection"><CollectionPage /></ToolBoundary>} />
        <Route path="/files/:fileId" element={<ToolBoundary key="file"><FilePage /></ToolBoundary>} />
        <Route path="/queue" element={<Navigate to="/intake" replace />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
