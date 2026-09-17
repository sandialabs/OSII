import { useMemo, useState } from "react";
import {
  Box, Button, InputAdornment, MenuItem, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, TextField, ToggleButton,
  ToggleButtonGroup, Typography,
} from "@mui/material";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ViewListOutlinedIcon from "@mui/icons-material/ViewListOutlined";
import GridViewOutlinedIcon from "@mui/icons-material/GridViewOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import type { FolderScopeDescriptor } from "../../../api/types";
import type { FileCardModel } from "../../../domain/files";
import { FileCard, formatFileSize, formatModifiedDate } from "../../files/components/FileCard";
import { FolderTile } from "./FolderTile";
import { compareBrowseFiles, compareNames, folderName, type BrowseSort } from "../contents";

type BrowseGridProps = {
  folders: FolderScopeDescriptor[];
  files: FileCardModel[];
  view: "list" | "icons";
  onChangeView: (view: "list" | "icons") => void;
  onOpenFolder: (folder: FolderScopeDescriptor) => void;
  onOpenFile: (fileId: string) => void;
};

type Entry = { kind: "folder"; folder: FolderScopeDescriptor } | { kind: "file"; file: FileCardModel };
const PAGE_SIZE = 48;

function fileType(file: FileCardModel): string {
  const extension = file.title.includes(".") ? file.title.split(".").pop()?.toUpperCase() : null;
  return extension ? `${extension} file` : "File";
}

export function BrowseGrid({ folders, files, view, onChangeView, onOpenFolder, onOpenFile }: BrowseGridProps) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<BrowseSort>("name-asc");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const entries = useMemo<Entry[]>(() => {
    const needle = query.trim().toLocaleLowerCase();
    const matchingFolders = folders.filter((folder) => folderName(folder).toLocaleLowerCase().includes(needle))
      .sort((a, b) => compareNames(folderName(a), folderName(b)) * (sort === "name-desc" ? -1 : 1));
    const matchingFiles = files.filter((file) => file.title.toLocaleLowerCase().includes(needle))
      .sort((a, b) => compareBrowseFiles(a, b, sort));
    return [
      ...matchingFolders.map((folder): Entry => ({ kind: "folder", folder })),
      ...matchingFiles.map((file): Entry => ({ kind: "file", file })),
    ];
  }, [folders, files, query, sort]);
  const visible = entries.slice(0, visibleCount);

  return (
    <Stack spacing={1.5}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
        <TextField
          size="small" label="Filter this folder" value={query}
          onChange={(event) => { setQuery(event.target.value); setVisibleCount(PAGE_SIZE); }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchOutlinedIcon fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1 }}
        />
        <TextField select size="small" label="Sort by" value={sort} sx={{ minWidth: 180 }}
          onChange={(event) => { setSort(event.target.value as BrowseSort); setVisibleCount(PAGE_SIZE); }}>
          <MenuItem value="name-asc">Name (A–Z)</MenuItem>
          <MenuItem value="name-desc">Name (Z–A)</MenuItem>
          <MenuItem value="modified-desc">Recently modified</MenuItem>
          <MenuItem value="size-desc">Largest first</MenuItem>
        </TextField>
        <ToggleButtonGroup exclusive size="small" value={view} aria-label="Folder view"
          onChange={(_, next: "list" | "icons" | null) => { if (next) onChangeView(next); }}>
          <ToggleButton value="list" aria-label="List view"><ViewListOutlinedIcon sx={{ mr: 0.5 }} />List</ToggleButton>
          <ToggleButton value="icons" aria-label="Icon view"><GridViewOutlinedIcon sx={{ mr: 0.5 }} />Icons</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <Typography variant="caption" color="text.secondary" role="status">
        {folders.length} folders · {files.length} files in this folder{query ? ` · ${entries.length} matches` : ""}. Folders appear first.
      </Typography>

      {entries.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 3 }}>
          {query ? "No names match this filter." : "This folder has no processed files or subfolders yet."}
        </Typography>
      ) : view === "list" ? (
        <TableContainer sx={{ border: 1, borderColor: "divider", borderRadius: 1, maxHeight: "65vh" }}>
          <Table size="small" stickyHeader aria-label="Current folder contents" sx={{ minWidth: 540, tableLayout: "fixed" }}>
            <TableHead><TableRow>
              <TableCell sx={{ width: "48%" }}>Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell align="right">Size</TableCell>
              <TableCell>Modified</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {visible.map((entry) => {
                const folder = entry.kind === "folder" ? entry.folder : null;
                const file = entry.kind === "file" ? entry.file : null;
                const name = folder ? folderName(folder) : file!.title;
                return (
                  <TableRow hover key={folder ? `folder:${folder.folder_id}` : `file:${file!.fileId}`}>
                    <TableCell sx={{ py: 0.5 }}>
                      <Button onClick={() => folder ? onOpenFolder(folder) : onOpenFile(file!.fileId)}
                        aria-label={`Open ${folder ? "folder" : "file"} ${name}`} title={name}
                        startIcon={folder ? <FolderOutlinedIcon sx={{ color: "warning.main" }} /> : <DescriptionOutlinedIcon color="action" />}
                        sx={{ color: "text.primary", fontWeight: folder ? 600 : 400, textTransform: "none", justifyContent: "flex-start", width: "100%", minWidth: 0 }}>
                        <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</Box>
                      </Button>
                    </TableCell>
                    <TableCell sx={{ color: "text.secondary" }}>{file ? fileType(file) : "Folder"}</TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{file ? formatFileSize(file.sizeBytes) ?? "—" : "—"}</TableCell>
                    <TableCell>{file ? formatModifiedDate(file.modifiedAt) ?? "—" : "—"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(170px, 100%), 1fr))", gap: 1.5 }}>
          {visible.map((entry) => entry.kind === "folder"
            ? <FolderTile key={`folder:${entry.folder.folder_id}`} folder={entry.folder} onOpen={() => onOpenFolder(entry.folder)} />
            : <FileCard key={`file:${entry.file.fileId}`} file={entry.file} compact onOpen={onOpenFile} />)}
        </Box>
      )}

      {entries.length > visibleCount ? (
        <Button variant="outlined" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>
          Show more ({visible.length} of {entries.length})
        </Button>
      ) : null}
    </Stack>
  );
}
