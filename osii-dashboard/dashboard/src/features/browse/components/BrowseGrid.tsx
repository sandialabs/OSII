import {
  Box, Button, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography,
} from "@mui/material";
import FolderOutlined from "@mui/icons-material/FolderOutlined";
import DescriptionOutlined from "@mui/icons-material/DescriptionOutlined";
import type { BrowseEntry } from "../../../api/catalogBrowse";
import { useFilePreviews } from "../../../hooks/useFileDisplay";
import { FileCard, formatFileSize, formatModifiedDate } from "../../files/components/FileCard";
import { folderLabel } from "../contents";
import { FolderTile } from "./FolderTile";

export function BrowseGrid({ entries, view, onOpenFolder, onOpenFile }: {
  entries: BrowseEntry[];
  view: "list" | "icons";
  onOpenFolder: (path: string) => void;
  onOpenFile: (id: string) => void;
}) {
  const previews = useFilePreviews(view === "icons" ? entries.flatMap(entry => entry.kind === "file" ? [entry.file_id] : []) : []);
  if (view === "icons") {
    return (
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(170px, 100%), 1fr))", gap: 1.5 }}>
        {entries.map(entry => {
          if (entry.kind === "folder") {
            return <FolderTile key={entry.path} name={folderLabel(entry.path)} onOpen={() => onOpenFolder(entry.path)} />;
          }
          const preview = previews.items[entry.file_id];
          return <FileCard key={entry.file_id} compact onOpen={onOpenFile} file={{
            fileId: entry.file_id,
            title: entry.name,
            subtitle: entry.path,
            sourceFileRelpath: entry.path,
            mime: entry.mime,
            sizeBytes: entry.size_bytes,
            modifiedAt: entry.mtime_utc,
            textPreview: preview?.text_preview,
            synthesisPreview: preview?.synthesis_preview ?? null,
            previewAvailable: entry.mime === "application/pdf",
            hasPreferredText: Boolean(preview?.text_preview),
            hasSynthesis: Boolean(preview?.synthesis_preview),
            hasEnrichments: false,
            supportsMarkdownRender: false,
          }} />;
        })}
      </Box>
    );
  }
  return (
    <TableContainer sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
      <Table size="small" aria-label="Folder contents" sx={{ tableLayout: "fixed" }}>
        <TableHead><TableRow>
          <TableCell sx={{ width: { xs: "72%", sm: "52%" } }}>Name</TableCell>
          <TableCell sx={{ display: { xs: "none", sm: "table-cell" } }}>Type</TableCell>
          <TableCell align="right">Size</TableCell>
          <TableCell sx={{ display: { xs: "none", sm: "table-cell" } }}>Modified</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {entries.map(entry => {
            const name = entry.kind === "folder" ? folderLabel(entry.path) : entry.name;
            const extension = name.slice(name.lastIndexOf(".") + 1).toUpperCase();
            const type = entry.kind === "folder" ? "Folder" : name.includes(".") && extension ? extension : "File";
            return (
              <TableRow hover key={entry.kind === "folder" ? "folder:" + entry.path : "file:" + entry.file_id}>
                <TableCell sx={{ py: 0.4, pl: 1 }}>
                  <Button fullWidth title={name} aria-label={"Open " + entry.kind + " " + name}
                    onClick={() => entry.kind === "folder" ? onOpenFolder(entry.path) : onOpenFile(entry.file_id)}
                    sx={{ justifyContent: "flex-start", color: "text.primary", textTransform: "none", minWidth: 0 }}>
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ minWidth: 0 }}>
                      {entry.kind === "folder" ? <FolderOutlined fontSize="small" color="warning" /> : <DescriptionOutlined fontSize="small" color="action" />}
                      <Typography noWrap variant="body2" fontWeight={entry.kind === "folder" ? 650 : 400}>{name}</Typography>
                    </Stack>
                  </Button>
                </TableCell>
                <TableCell sx={{ display: { xs: "none", sm: "table-cell" }, color: "text.secondary" }}>{type}</TableCell>
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{entry.kind === "file" ? formatFileSize(entry.size_bytes) ?? "—" : "—"}</TableCell>
                <TableCell sx={{ display: { xs: "none", sm: "table-cell" } }}>{entry.kind === "file" ? formatModifiedDate(entry.mtime_utc) ?? "—" : "—"}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
