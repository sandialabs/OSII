// src/features/browse/components/BrowseGrid.tsx
import {
  Grid,
  Stack,
  Typography,
} from "@mui/material";

import type { FolderScopeDescriptor } from "../../../api/types";
import type { FileCardModel } from "../../../domain/files";
import { FolderTile } from "./FolderTile";
import { FileTile } from "./FileTile";

type BrowseGridProps = {
  folders: FolderScopeDescriptor[];
  files: FileCardModel[];
  selectedFolderId?: string | null;
  onOpenFolder: (folder: FolderScopeDescriptor) => void;
  onOpenFile: (fileId: string) => void;
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

          <Grid container spacing={1.5}>
            {folders.map((folder) => (
              <Grid item xs={12} sm={6} md={4} lg={3} xl={2} key={folder.folder_id}>
                <FolderTile
                  folder={folder}
                  selected={selectedFolderId === folder.folder_id}
                  onOpen={() => onOpenFolder(folder)}
                />
              </Grid>
            ))}
          </Grid>
        </Stack>
      ) : null}

      {files.length > 0 ? (
        <Stack spacing={1}>
          <Typography variant="subtitle2" fontWeight={600}>
            Files
          </Typography>

          <Grid container spacing={1.5}>
            {files.map((file) => (
              <Grid item xs={12} sm={6} md={4} lg={3} xl={2} key={file.fileId}>
                <FileTile file={file} onOpen={onOpenFile} />
              </Grid>
            ))}
          </Grid>
        </Stack>
      ) : null}
    </Stack>
  );
}