// src/features/home/pages/HomePage.tsx
import { Alert, Button, Paper, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useMemo, useState } from "react";

import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import { toFileCardModel } from "../../../domain/files";
import { FileGrid } from "../../files/components/FileGrid";
import { buildFileRoute } from "../../../utils/routes";
import { LibraryInsights } from "../components/LibraryInsights";
import { MetadataSearchDrawer } from "../components/MetadataSearchDrawer";
import { emptyFileFilters, fileFormat, filterFiles } from "../../../domain/fileFilters";

export function HomePage() {
  const navigate = useNavigate();
  const [searchOpen, setSearchOpen] = useState(false);
  const [filters, setFilters] = useState({ ...emptyFileFilters });
  const { data, isLoading, isError, error } = useScopeSummaries({
    scope_type: "root",
  });

  const files = useMemo(() => (data?.summaries ?? []).map(toFileCardModel), [data]);
  const result = useMemo(() => filterFiles(files, filters), [files, filters]);
  const formats = [...new Set(files.map(fileFormat))].sort();
  const filtered = Object.keys(emptyFileFilters).some(key => filters[key as keyof typeof filters] !== emptyFileFilters[key as keyof typeof filters]);

  return (
    <Stack spacing={2}>
      {!isLoading && !isError && !files.length ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Stack spacing={0.25}>
              <Typography variant="h6" fontWeight={700}>Start your first OSII library</Typography>
              <Typography variant="body2" color="text.secondary">
                OSII keeps your original files in their source folder and builds inspectable, reusable results beside them. Basic reading and lexical search work without a model connection.
              </Typography>
            </Stack>
            <Alert severity="info">
              Choose your source folder and optional services in the launcher, then use <strong>Intake</strong> to process files. Open <strong>Setup</strong> only to add a model connection or change processing rules. In a local development session, <code>make dev</code> uses <code>osii-data/source</code> by default.
            </Alert>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <Button variant="outlined" onClick={() => navigate("/admin/processors")}>Open Setup</Button>
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
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => setSearchOpen(true)}>Search metadata{filtered ? " · filters active" : ""}</Button>
          {filtered && <Button onClick={() => setFilters({ ...emptyFileFilters })}>Clear filters</Button>}
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Browse all files in a compact flat view. Use Browse for native folder hierarchy navigation.
        </Typography>
      </Stack>

      <FileGrid
        files={result.files}
        title="All Files"
        subtitle={`${result.files.length} of ${files.length} files`}
        isLoading={isLoading}
        isError={isError}
        error={error}
        emptyMessage={result.error || "No files match these metadata filters."}
        onOpen={(fileId) => navigate(buildFileRoute({ fileId }))}
      />
      <MetadataSearchDrawer open={searchOpen} onClose={() => setSearchOpen(false)} filters={filters} onChange={setFilters} formats={formats} count={result.files.length} error={result.error} />
    </Stack>
  );
}
