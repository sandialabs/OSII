// src/app/router.tsx
import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./layout/AppLayout";
import { HomePage } from "../features/home/pages/HomePage";
import { BrowsePage } from "../features/browse/pages/BrowsePage";
import { SearchPage } from "../features/search/pages/SearchPage";
import { ChatPage } from "../features/chat/pages/ChatPage";
import { CollectionsPage } from "../features/collections/pages/CollectionsPage";
import { CollectionPage } from "../features/collections/pages/CollectionPage";
import { FilePage } from "../features/files/pages/FilePage";
import { QueuePage } from "../features/queue/pages/QueuePage";
import { ProcessorsPage } from "../features/admin/pages/ProcessorsPage";

function NotFoundPage() {
  return <Navigate to="/" replace />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="/browse" element={<BrowsePage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/collections" element={<CollectionsPage />} />
        <Route path="/collections/:collectionId" element={<CollectionPage />} />
        <Route path="/files/:fileId" element={<FilePage />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/admin/processors" element={<ProcessorsPage />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
