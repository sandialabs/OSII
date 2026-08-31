// src/features/files/components/FileActionBar.tsx
import { useState } from "react";
import {
  Button,
  Card,
  CardContent,
  Stack,
  Typography,
} from "@mui/material";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import CollectionsBookmarkOutlinedIcon from "@mui/icons-material/CollectionsBookmarkOutlined";
import LocalOfferOutlinedIcon from "@mui/icons-material/LocalOfferOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import { useNavigate } from "react-router-dom";

import { getObjectSourceUrl } from "../../../api/source";
import { AddFileToCollectionDialog } from "../../collections/components/AddFileToCollectionDialog";
import { ManualKeywordsDialog } from "./ManualKeywordsDialog";
import { DeleteObjectDialog } from "./DeleteObjectDialog";

type FileActionBarProps = {
  fileId: string;
};

export function FileActionBar({ fileId }: FileActionBarProps) {
  const navigate = useNavigate();
  const [collectionDialogOpen, setCollectionDialogOpen] = useState(false);
  const [keywordsDialogOpen, setKeywordsDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  return (
    <>
      <Stack spacing={2}>
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="subtitle1" fontWeight={600}>
                File management
              </Typography>

              <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} flexWrap="wrap" useFlexGap>
                <Button
                  variant="outlined"
                  startIcon={<OpenInNewOutlinedIcon />}
                  component="a"
                  href={getObjectSourceUrl(fileId)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Original File
                </Button>

                <Button
                  variant="outlined"
                  startIcon={<CollectionsBookmarkOutlinedIcon />}
                  onClick={() => setCollectionDialogOpen(true)}
                >
                  Add to Collection
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<LocalOfferOutlinedIcon />}
                  onClick={() => setKeywordsDialogOpen(true)}
                >
                  Labels & Tags
                </Button>
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteOutlineOutlinedIcon />}
                  onClick={() => setDeleteDialogOpen(true)}
                >
                  Delete File Data
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      </Stack>

      <AddFileToCollectionDialog
        open={collectionDialogOpen}
        onClose={() => setCollectionDialogOpen(false)}
        fileId={fileId}
      />
      <ManualKeywordsDialog
        open={keywordsDialogOpen}
        onClose={() => setKeywordsDialogOpen(false)}
        fileId={fileId}
      />
      <DeleteObjectDialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onDeleted={() => navigate("/files")}
        fileId={fileId}
      />
    </>
  );
}
