// src/features/chat/pages/ChatPage.tsx
import { useMemo } from "react";
import { Stack, Typography } from "@mui/material";
import { useSearchParams } from "react-router-dom";

import type { ScopeDescribeRequest } from "../../../api/types";
import { ChatPanel } from "../components/ChatPanel";

function deriveScope(searchParams: URLSearchParams): ScopeDescribeRequest {
  const scopeType = searchParams.get("scope_type");

  if (scopeType === "folder") {
    const folderId = searchParams.get("folder_id");
    if (folderId) {
      return { scope_type: "folder", folder_id: folderId };
    }
  }

  if (scopeType === "collection") {
    const collectionId = searchParams.get("collection_id");
    if (collectionId) {
      return { scope_type: "collection", collection_id: collectionId };
    }
  }

  if (scopeType === "object") {
    const fileId = searchParams.get("file_id");
    if (fileId) {
      return { scope_type: "object", file_id: fileId };
    }
  }

  return { scope_type: "root" };
}

export function ChatPage() {
  const [searchParams] = useSearchParams();

  const scope = useMemo(
    () => deriveScope(searchParams),
    [searchParams],
  );

  return (
    <Stack spacing={2.5}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>
          Chat
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Ask grounded questions, get concise answers, and jump directly to supporting evidence.
        </Typography>
      </Stack>

      <ChatPanel scope={scope} />
    </Stack>
  );
}