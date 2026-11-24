import { useState } from "react";
import {
  Alert, Button, InputAdornment, LinearProgress, MenuItem, Stack, TextField, ToggleButton,
  ToggleButtonGroup, Typography,
} from "@mui/material";
import SearchOutlined from "@mui/icons-material/SearchOutlined";
import ViewListOutlined from "@mui/icons-material/ViewListOutlined";
import GridViewOutlined from "@mui/icons-material/GridViewOutlined";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { browseCatalog, type BrowseSort } from "../../../api/catalogBrowse";
import { listFolderScopes } from "../../../api/scopes";
import { buildFileRoute } from "../../../utils/routes";
import { BrowseExplorer } from "../components/BrowseExplorer";
import { BrowseGrid } from "../components/BrowseGrid";
import { normalizeFolderPath } from "../contents";

const PAGE_SIZE = 48;
type View = "list" | "icons";

function FolderListing({ path, view, onNavigate, onChangeView }: {
  path: string;
  view: View;
  onNavigate: (path: string) => void;
  onChangeView: (view: View) => void;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<BrowseSort>("name-asc");
  const [offset, setOffset] = useState(0);
  const folder = useQuery({
    queryKey: ["catalog-browse", path, query.trim(), sort, offset],
    queryFn: ({ signal }) => browseCatalog(path, { query, sort, offset, signal }),
  });
  const entries = folder.data?.items ?? [];

  return (
    <BrowseExplorer path={path} sourceName={folder.data?.source_name ?? ""}
      onNavigate={onNavigate} onRefresh={() => void folder.refetch()}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
          <TextField size="small" label={path ? "Filter this folder" : "Filter names"} value={query}
            onChange={event => { setQuery(event.target.value); setOffset(0); }} inputProps={{ maxLength: 256 }}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchOutlined fontSize="small" /></InputAdornment> }}
            sx={{ flex: "1 1 190px" }} />
          <TextField select size="small" label="Sort by" value={sort} sx={{ minWidth: 145 }}
            onChange={event => { setSort(event.target.value as BrowseSort); setOffset(0); }}>
            <MenuItem value="name-asc">Name (A–Z)</MenuItem>
            <MenuItem value="name-desc">Name (Z–A)</MenuItem>
            <MenuItem value="modified-desc">Recently modified</MenuItem>
            <MenuItem value="size-desc">Largest first</MenuItem>
          </TextField>
          <ToggleButtonGroup exclusive size="small" value={view} aria-label="Folder view"
            onChange={(_, next: View | null) => { if (next) onChangeView(next); }}>
            <ToggleButton value="list" aria-label="List view"><ViewListOutlined fontSize="small" /></ToggleButton>
            <ToggleButton value="icons" aria-label="Icon view"><GridViewOutlined fontSize="small" /></ToggleButton>
          </ToggleButtonGroup>
        </Stack>
        {folder.isPending ? <LinearProgress aria-label="Loading folder contents" />
          : folder.isError ? <Alert severity="error" action={<Button onClick={() => void folder.refetch()}>Retry</Button>}>Could not load this folder.</Alert>
          : entries.length ? <BrowseGrid entries={entries} view={view} onOpenFolder={onNavigate} onOpenFile={fileId => navigate(buildFileRoute({ fileId }))} />
          : <Typography color="text.secondary" sx={{ py: 2 }}>{query.trim() ? "No matching names." : "No files here yet."}</Typography>}
        {(offset > 0 || folder.data?.has_more) && <Stack direction="row" spacing={1} alignItems="center">
          <Button size="small" disabled={!offset || folder.isFetching} onClick={() => setOffset(offset - PAGE_SIZE)}>Previous</Button>
          <Typography variant="body2" color="text.secondary">Page {offset / PAGE_SIZE + 1}</Typography>
          <Button size="small" disabled={!folder.data?.has_more || folder.isFetching} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button>
        </Stack>}
      </Stack>
    </BrowseExplorer>
  );
}

export function BrowsePage() {
  const [params, setParams] = useSearchParams();
  const pathParam = params.get("path");
  const folderId = params.get("folder_id");
  const view = params.get("view") === "icons" ? "icons" : "list";
  const legacyPath = useQuery({
    queryKey: ["catalog-browse-legacy", folderId],
    enabled: pathParam === null && Boolean(folderId),
    queryFn: async ({ signal }) => {
      const { scopes } = await listFolderScopes();
      const folder = scopes.find(item => item.folder_id === folderId);
      const path = normalizeFolderPath(folder?.path ?? "");
      if (!path) return path;
      const result = await browseCatalog(path, { signal });
      // Older sidecar folder records were relative to the configured source
      // while document records can include the source folder as a prefix.
      return result.items.length || !result.source_name || path.startsWith("external/")
        ? path : result.source_name + "/" + path;
    },
  });
  if (legacyPath.fetchStatus !== "idle" && legacyPath.isPending) return <LinearProgress aria-label="Loading folder" />;
  const path = normalizeFolderPath(pathParam ?? legacyPath.data ?? "");
  const openFolder = (next: string) => {
    const updated = new URLSearchParams(params);
    updated.delete("folder_id");
    if (next) updated.set("path", next);
    else updated.delete("path");
    setParams(updated);
  };

  return <FolderListing key={path} path={path} view={view} onNavigate={openFolder}
    onChangeView={next => {
      const updated = new URLSearchParams(params);
      updated.set("view", next);
      setParams(updated, { replace: true });
    }} />;
}
