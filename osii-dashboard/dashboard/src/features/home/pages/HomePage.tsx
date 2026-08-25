// src/features/home/pages/HomePage.tsx
import { Alert, Button, Paper, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import { toFileCardModel } from "../../../domain/files";
import { FileGrid } from "../../files/components/FileGrid";
import { buildFileRoute } from "../../../utils/routes";
import { LibraryInsights } from "../components/LibraryInsights";

export function HomePage() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useScopeSummaries({
    scope_type: "root",
  });

  const files = (data?.summaries ?? []).map(toFileCardModel);

  return (
    <Stack spacing={2}>
      {!isLoading && !isError && !files.length ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Stack spacing={0.25}>
              <Typography variant="h6" fontWeight={700}>Start your first OSII library</Typography>
              <Typography variant="body2" color="text.secondary">
                <code>make dev</code> started OSII&apos;s dashboard, backend, Python text extraction, no-AI previews, lexical search tools, and local enrichments. Ollama and Tesseract are optional programs that must be installed separately.
              </Typography>
            </Stack>
            <Alert severity="info">
              First check <strong>Tools &amp; services</strong> to see exactly what is running. Then put documents in <code>osii-data/source</code> and use <strong>Intake</strong>.
            </Alert>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <Button variant="outlined" onClick={() => navigate("/admin/processors")}>Review tools &amp; services</Button>
              <Button variant="contained" onClick={() => navigate("/intake")}>Open Intake</Button>
            </Stack>
          </Stack>
        </Paper>
      ) : null}

      <LibraryInsights />

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
