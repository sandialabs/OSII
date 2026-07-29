// src/features/files/components/ScopeFileBrowser.tsx
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { toFileCardModel } from "../../../domain/files";
import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import type { ScopeDescribeRequest } from "../../../api/types";
import { buildFileRoute } from "../../../utils/routes";
import { FileGrid } from "./FileGrid";

type ScopeFileBrowserProps = {
  scope: ScopeDescribeRequest;
  title?: string;
  subtitle?: string;
  emptyMessage?: string;
};

export function ScopeFileBrowser({
  scope,
  title,
  subtitle,
  emptyMessage,
}: ScopeFileBrowserProps) {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useScopeSummaries(scope);

  const files = useMemo(
    () => (data?.summaries ?? []).map(toFileCardModel),
    [data?.summaries],
  );

  return (
    <FileGrid
      files={files}
      title={title}
      subtitle={subtitle}
      emptyMessage={emptyMessage}
      isLoading={isLoading}
      isError={isError}
      error={error}
      onOpen={(fileId) => navigate(buildFileRoute({ fileId }))}
    />
  );
}