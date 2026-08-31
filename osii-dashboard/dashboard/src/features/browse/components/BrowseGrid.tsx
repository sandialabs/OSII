// src/features/browse/components/BrowseGrid.tsx
import {
  Box,
  Stack,
  Typography,
} from "@mui/material";

import type { FolderScopeDescriptor } from "../../../api/types";
import type { FileCardModel } from "../../../domain/files";
import { FileGrid } from "../../files/components/FileGrid";
import { FolderTile } from "./FolderTile";

type BrowseGridProps = {
  folders: FolderScopeDescriptor[];
  files: FileCardModel[];
  selectedFolderId?: string | null;
  onOpenFolder: (folder: FolderScopeDescriptor) => void;
  onOpenFile: (fileId: string) => void;
};

const tileGridSx = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(min(220px, 100%), 1fr))",
  gap: 1.5,
};

export function BrowseGrid({
  folders,
  files,
  selectedFolderId = null,
  onOpenFolder,
  onOpenFile,
}: BrowseGridProps) {
  if (folders.length === 0 && files.length === 0) {
    return (
      <Typography color="text.secondary">
        Nothing is available in this folder.
      </Typography>
    );
  }

  return (
    <Stack spacing={1.5}>
      {folders.length > 0 ? (
        <Stack spacing={1}>
          <Typography variant="subtitle2" fontWeight={600}>
            Folders
          </Typography>

          <Box sx={tileGridSx}>
            {folders.map((folder) => (
              <Box key={folder.folder_id}>
                <FolderTile
                  folder={folder}
                  selected={selectedFolderId === folder.folder_id}
                  onOpen={() => onOpenFolder(folder)}
                />
              </Box>
            ))}
          </Box>
        </Stack>
      ) : null}

      {files.length > 0 ? (
        <FileGrid files={files} title="Files" onOpen={onOpenFile} />
      ) : null}
    </Stack>
  );
}
