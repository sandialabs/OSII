import { Button, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useMemo, useState } from "react";

import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import { toFileCardModel } from "../../../domain/files";
import { FileGrid } from "../../files/components/FileGrid";
import { buildFileRoute } from "../../../utils/routes";
import { MetadataSearchDrawer } from "../components/MetadataSearchDrawer";
import { emptyFileFilters, fileFormat, filterFiles } from "../../../domain/fileFilters";

export function FilesPage() {
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
  const fileCount = files.length.toLocaleString();
  const count = filtered ? `${result.files.length.toLocaleString()} of ${fileCount}` : fileCount;

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" alignItems="center" spacing={1} useFlexGap flexWrap="wrap">
        <Typography component="h1" variant="h5" fontWeight={700}>
          Files
        </Typography>
        {data && (
          <Typography role="status" variant="body2" color="text.secondary">
            {count} {files.length === 1 ? "file" : "files"}
          </Typography>
        )}
        <Button size="small" variant={filtered ? "contained" : "outlined"} onClick={() => setSearchOpen(true)}>
          Search metadata
        </Button>
        {filtered && <Button size="small" onClick={() => setFilters({ ...emptyFileFilters })}>Clear filters</Button>}
      </Stack>

      <FileGrid
        files={result.files}
        isLoading={isLoading}
        isError={isError}
        error={error}
        emptyMessage={result.error || (filtered ? "No files match these metadata filters." : "No files yet.")}
        onOpen={(fileId) => navigate(buildFileRoute({ fileId }))}
      />
      <MetadataSearchDrawer open={searchOpen} onClose={() => setSearchOpen(false)} filters={filters} onChange={setFilters} formats={formats} count={result.files.length} error={result.error} />
    </Stack>
  );
}
