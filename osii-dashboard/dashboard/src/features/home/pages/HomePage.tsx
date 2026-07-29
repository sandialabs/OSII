// src/features/home/pages/HomePage.tsx
import { Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import { toFileCardModel } from "../../../domain/files";
import { FileGrid } from "../../files/components/FileGrid";
import { buildFileRoute } from "../../../utils/routes";

export function HomePage() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useScopeSummaries({
    scope_type: "root",
  });

  const files = (data?.summaries ?? []).map(toFileCardModel);

  return (
    <Stack spacing={2}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>
          Files
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Browse all files in a compact flat view. Use Browse for native folder hierarchy navigation.
        </Typography>
      </Stack>

      <FileGrid
        files={files}
        title="All Files"
        subtitle={`${files.length} files`}
        isLoading={isLoading}
        isError={isError}
        error={error}
        emptyMessage="No files were found."
        onOpen={(fileId) => navigate(buildFileRoute({ fileId }))}
      />
    </Stack>
  );
}