// src/features/browse/components/BrowseDetailsPane.tsx
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";

import type { FolderScopeDescriptor, ObjectSummary } from "../../../api/types";
import { useScopeArtifacts } from "../../../hooks/useScopeArtifacts";

export type BrowseSelection =
  | {
      kind: "none";
    }
  | {
      kind: "folder";
      folder: FolderScopeDescriptor;
    }
  | {
      kind: "file";
      file: ObjectSummary;
    };

type BrowseDetailsPaneProps = {
  selection: BrowseSelection;
};

export function BrowseDetailsPane({ selection }: BrowseDetailsPaneProps) {
  if (selection.kind === "none") {
    return (
      <Card>
        <CardContent>
          <Typography variant="body2" color="text.secondary">
            Select a folder or file to see brief details here.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  if (selection.kind === "folder") {
    return <FolderDetails folder={selection.folder} />;
  }

  return <FileDetails file={selection.file} />;
}

function FolderDetails({ folder }: { folder: FolderScopeDescriptor }) {
  const { data, isLoading, isError, error } = useScopeArtifacts(
    {
      scope_type: "folder",
      folder_id: folder.folder_id,
    },
    true,
  );

  return (
    <Card>
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} alignItems="center">
            <FolderOutlinedIcon color="primary" fontSize="small" />
            <Typography variant="subtitle1" fontWeight={600}>
              {folder.label}
            </Typography>
          </Stack>

          <Typography variant="body2" color="text.secondary">
            Path: {folder.path || "root"}
          </Typography>

          <Typography variant="caption" color="text.secondary">
            Folder ID: {folder.folder_id}
          </Typography>

          {isLoading ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={16} />
              <Typography variant="body2" color="text.secondary">
                Loading folder summary…
              </Typography>
            </Stack>
          ) : isError ? (
            <Alert severity="warning">
              Failed to load folder artifact summary.
              {error instanceof Error ? ` ${error.message}` : ""}
            </Alert>
          ) : data ? (
            <>
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                <Chip label={`${data.artifact_summary.member_count} items`} size="small" />
                {data.artifact_summary.has_synthesis ? (
                  <Chip label="Has synthesis" size="small" />
                ) : null}
                {data.artifact_summary.has_enrichments ? (
                  <Chip label="Has enrichments" size="small" variant="outlined" />
                ) : null}
              </Stack>

              <Typography variant="subtitle2" fontWeight={600}>
                Synthesis
              </Typography>

              <Box
                sx={{
                  maxHeight: 240,
                  overflowY: "auto",
                  overflowX: "hidden",
                  p: 1,
                  borderRadius: 1,
                  backgroundColor: "rgba(15,23,42,0.04)",
                }}
              >
                <Typography
                  variant="body2"
                  sx={{
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  {data.artifact_summary.synthesis_preview ?? "No synthesis preview available."}
                </Typography>
              </Box>

              {data.artifact_summary.syntheses.length > 0 ? (
                <Stack spacing={0.5}>
                  <Typography variant="caption" color="text.secondary">
                    Available syntheses
                  </Typography>
                  {data.artifact_summary.syntheses.map((item) => (
                    <Typography
                      key={`${item.name}-${item.relpath}`}
                      variant="caption"
                      color="text.secondary"
                    >
                      {item.name}
                    </Typography>
                  ))}
                </Stack>
              ) : null}
            </>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
}

function FileDetails({ file }: { file: ObjectSummary }) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} alignItems="center">
            <DescriptionOutlinedIcon color="action" fontSize="small" />
            <Typography variant="subtitle1" fontWeight={600}>
              {file.filename ?? file.file_id}
            </Typography>
          </Stack>

          <Typography variant="body2" color="text.secondary">
            {file.source_relpath ?? "No source path"}
          </Typography>

          {file.mime ? (
            <Typography variant="caption" color="text.secondary">
              MIME: {file.mime}
            </Typography>
          ) : null}

          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            {file.has_synthesis ? (
              <Chip label="Has synthesis" size="small" />
            ) : null}

            {file.has_preferred_text ? (
              <Chip label="Has text" size="small" variant="outlined" />
            ) : null}

            {file.has_enrichments ? (
              <Chip label="Has enrichments" size="small" variant="outlined" />
            ) : null}
          </Stack>

          <Typography variant="subtitle2" fontWeight={600}>
            Synthesis
          </Typography>

          <Box
            sx={{
              maxHeight: 240,
              overflowY: "auto",
              overflowX: "hidden",
              p: 1,
              borderRadius: 1,
              backgroundColor: "rgba(15,23,42,0.04)",
            }}
          >
            <Typography
              variant="body2"
              sx={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {file.synthesis_preview ?? "No synthesis preview available."}
            </Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}