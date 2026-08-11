// src/features/files/components/GroundedSegmentEditor.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  IconButton,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import RestartAltOutlinedIcon from "@mui/icons-material/RestartAltOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import KeyboardArrowUpOutlinedIcon from "@mui/icons-material/KeyboardArrowUpOutlined";
import KeyboardArrowDownOutlinedIcon from "@mui/icons-material/KeyboardArrowDownOutlined";
import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";

import { useEditedObjectText } from "../../../hooks/useEditedObjectText";
import { useSaveEditedObjectText } from "../../../hooks/useSaveEditedObjectText";
import { useDeleteEditedObjectText } from "../../../hooks/useDeleteEditedObjectText";
import type { ManifestRecord } from "../../../api/types";

type GroundedSegmentEditorProps = {
  fileId: string;
  segments: ManifestRecord[];
  canonicalText: string;
  activeSegmentId?: string | null;
  onJumpToSource?: (params: { page?: number | null; segmentId?: string | null }) => void;
  height?: number | string;
  fontSizePx?: number;
  searchResetToken?: number;
  compact?: boolean;
};

type EditableSegment = {
  id: string;
  text: string;
  canonicalText: string;
  page: number | null;
  kind: string;
  type: string | null;
};

function extractCanonicalSegmentText(
  canonicalText: string,
  segment: ManifestRecord,
): string {
  const start = segment.span?.char_start;
  const end = segment.span?.char_end;

  if (
    typeof start !== "number" ||
    typeof end !== "number" ||
    start < 0 ||
    end < start
  ) {
    return "";
  }

  return canonicalText.slice(start, end);
}

function buildBaseSegments(
  segments: ManifestRecord[],
  canonicalText: string,
): EditableSegment[] {
  return segments
    .filter((segment) => segment.kind === "text")
    .map((segment) => ({
      id: segment.id,
      text: "",
      canonicalText: extractCanonicalSegmentText(canonicalText, segment),
      page:
        typeof segment.source_origin?.page === "number"
          ? segment.source_origin.page
          : null,
      kind: segment.kind,
      type: typeof segment.type === "string" ? segment.type : null,
    }));
}

export function GroundedSegmentEditor({
  fileId,
  segments,
  canonicalText,
  activeSegmentId = null,
  onJumpToSource,
  height = "68vh",
  fontSizePx = 15,
  searchResetToken = 0,
  compact = false,
}: GroundedSegmentEditorProps) {
  const editedQuery = useEditedObjectText(fileId, true);
  const saveMutation = useSaveEditedObjectText(fileId);
  const deleteMutation = useDeleteEditedObjectText(fileId);

  const baseSegments = useMemo(
    () => buildBaseSegments(segments, canonicalText),
    [segments, canonicalText],
  );

  const [draftSegments, setDraftSegments] = useState<EditableSegment[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [activeMatchIndex, setActiveMatchIndex] = useState(0);

  const segmentRefs = useRef<Record<string, HTMLElement | null>>({});
  useEffect(() => {
    const editedById = new Map(
      (editedQuery.data?.segments ?? []).map((segment) => [segment.id, segment.text]),
    );

    const next = baseSegments.map((segment) => ({
      ...segment,
      text: editedById.get(segment.id) ?? segment.canonicalText,
    }));

    setDraftSegments(next);
  }, [baseSegments, editedQuery.data?.segments]);

  const matchingSegments = useMemo(() => {
    const needle = submittedSearch.trim().toLowerCase();
    if (!needle) return [];

    return draftSegments.filter((segment) =>
      segment.text.toLowerCase().includes(needle),
    );
  }, [draftSegments, submittedSearch]);

  const activeSearchSegmentId =
    matchingSegments.length > 0
      ? matchingSegments[Math.min(activeMatchIndex, matchingSegments.length - 1)]?.id ?? null
      : null;

  useEffect(() => {
    setActiveMatchIndex(0);
  }, [submittedSearch]);

  useEffect(() => {
    if (!searchResetToken) return;
    setSubmittedSearch("");
    setActiveMatchIndex(0);
  }, [searchResetToken]);

  useEffect(() => {
    const targetId = activeSearchSegmentId || activeSegmentId;
    if (!targetId) return;

    const node = segmentRefs.current[targetId];
    if (node) {
      node.scrollIntoView({
        block: "center",
        behavior: "smooth",
      });
    }
  }, [activeSegmentId, activeSearchSegmentId]);

  useEffect(() => {
    if (!activeSearchSegmentId) return;

    const match = matchingSegments.find((segment) => segment.id === activeSearchSegmentId);
    if (!match) return;

    onJumpToSource?.({
      page: match.page,
      segmentId: match.id,
    });
  }, [activeSearchSegmentId, matchingSegments, onJumpToSource]);

  const handleChangeSegmentText = (id: string, text: string) => {
    setDraftSegments((prev) =>
      prev.map((segment) =>
        segment.id === id ? { ...segment, text } : segment,
      ),
    );
  };

  const handleSave = async () => {
    await saveMutation.mutateAsync({
      segments: draftSegments.map((segment) => ({
        id: segment.id,
        text: segment.text,
      })),
    });

    setIsEditing(false);
  };

  const handleResetEdited = async () => {
    await deleteMutation.mutateAsync();
    setIsEditing(false);
  };

  const hasEditedText = Boolean(editedQuery.data?.exists);

  const goToPreviousMatch = () => {
    if (matchingSegments.length === 0) return;
    setActiveMatchIndex((prev) =>
      prev <= 0 ? matchingSegments.length - 1 : prev - 1,
    );
  };

  const goToNextMatch = () => {
    if (matchingSegments.length === 0) return;
    setActiveMatchIndex((prev) =>
      prev >= matchingSegments.length - 1 ? 0 : prev + 1,
    );
  };

  const handleSubmitSearch = () => {
    setSubmittedSearch(searchInput.trim());
  };

  const handleCloseSearch = () => {
    setSearchOpen(false);
    setSearchInput("");
    setSubmittedSearch("");
    setActiveMatchIndex(0);
  };

  return (
    <Stack spacing={1.25} sx={{ minWidth: 0 }}>
      <Stack
        direction={compact ? "column" : { xs: "column", md: "row" }}
        spacing={1.25}
        justifyContent="space-between"
        alignItems={compact ? "flex-start" : { xs: "flex-start", md: "center" }}
      >
        <Stack spacing={0.25}>
          <Typography variant="subtitle1" fontWeight={600}>
            Grounded Text
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Click a segment to jump to the grounded PDF page.
          </Typography>
        </Stack>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          <IconButton
            size="small"
            onClick={() => setSearchOpen((prev) => !prev)}
            sx={{
              border: "1px solid rgba(15,23,42,0.14)",
              borderRadius: 1,
            }}
          >
            <SearchOutlinedIcon fontSize="small" />
          </IconButton>

          {!isEditing ? (
            <Button
              size="small"
              variant="outlined"
              startIcon={<EditOutlinedIcon />}
              onClick={() => setIsEditing(true)}
            >
              Edit Text
            </Button>
          ) : (
            <>
              <Button
                size="small"
                variant="contained"
                startIcon={<SaveOutlinedIcon />}
                onClick={() => void handleSave()}
                disabled={saveMutation.isPending}
              >
                Save
              </Button>
              <Button
                size="small"
                variant="outlined"
                onClick={() => setIsEditing(false)}
              >
                Cancel
              </Button>
            </>
          )}

          <Button
            size="small"
            variant="outlined"
            color="warning"
            startIcon={<RestartAltOutlinedIcon />}
            onClick={() => void handleResetEdited()}
            disabled={!hasEditedText || deleteMutation.isPending}
          >
            Restore
          </Button>
        </Stack>
      </Stack>

      {searchOpen ? (
        <Card>
          <CardContent sx={{ py: 1.25 }}>
            <Stack spacing={1.25}>
              <Stack
                direction={compact ? "column" : { xs: "column", md: "row" }}
                spacing={1}
                alignItems={compact ? "stretch" : { xs: "stretch", md: "center" }}
              >
                <TextField
                  fullWidth
                  size="small"
                  label="Find in file"
                  placeholder="Search this file’s grounded segments"
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                />

                <IconButton
                  size="small"
                  color="primary"
                  onClick={handleSubmitSearch}
                  disabled={!searchInput.trim()}
                  sx={{
                    border: "1px solid rgba(20,184,166,0.25)",
                    borderRadius: 1,
                    alignSelf: compact ? "flex-start" : { xs: "flex-start", md: "center" },
                  }}
                >
                  <SearchOutlinedIcon fontSize="small" />
                </IconButton>

                <Stack direction="row" spacing={1} alignItems="center">
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<KeyboardArrowUpOutlinedIcon />}
                    onClick={goToPreviousMatch}
                    disabled={matchingSegments.length === 0}
                  >
                    Prev
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    endIcon={<KeyboardArrowDownOutlinedIcon />}
                    onClick={goToNextMatch}
                    disabled={matchingSegments.length === 0}
                  >
                    Next
                  </Button>
                </Stack>

                <IconButton size="small" onClick={handleCloseSearch}>
                  <CloseOutlinedIcon fontSize="small" />
                </IconButton>
              </Stack>

              {submittedSearch ? (
                <Typography variant="caption" color="text.secondary">
                  {matchingSegments.length === 0
                    ? "No matching segments found."
                    : `Match ${Math.min(activeMatchIndex + 1, matchingSegments.length)} of ${matchingSegments.length}`}
                </Typography>
              ) : null}
            </Stack>
          </CardContent>
        </Card>
      ) : null}

      {hasEditedText ? (
        <Alert severity="info">
          Edited text is present and is now the preferred text representation.
        </Alert>
      ) : null}

      {saveMutation.isSuccess ? (
        <Alert severity="warning">
          Edited text saved. Embeddings and search chunks are stale and should be rebuilt.
        </Alert>
      ) : null}

      {saveMutation.isError ? (
        <Alert severity="error">
          {saveMutation.error instanceof Error
            ? saveMutation.error.message
            : "Failed to save edited text."}
        </Alert>
      ) : null}

      {deleteMutation.isError ? (
        <Alert severity="error">
          {deleteMutation.error instanceof Error
            ? deleteMutation.error.message
            : "Failed to remove edited text."}
        </Alert>
      ) : null}

      <Card sx={{ minWidth: 0 }}>
        <CardContent sx={{ p: 0 }}>
          <Box
            sx={{
              height,
              overflowY: "auto",
              overflowX: "hidden",
              px: 1.25,
              py: 1.25,
            }}
          >
            <Stack spacing={1}>
              {draftSegments.length === 0 ? (
                <Typography color="text.secondary">
                  No grounded text segments are available for this file.
                </Typography>
              ) : (
                draftSegments.map((segment) => {
                  const isExternallyActive = activeSegmentId === segment.id;
                  const isSearchActive = activeSearchSegmentId === segment.id;
                  const isActive = isExternallyActive || isSearchActive;

                  return (
                    <Box
                      key={segment.id}
                      ref={(node) => {
                        segmentRefs.current[segment.id] = node as HTMLElement | null;
                      }}
                      onClick={() => {
                        onJumpToSource?.({
                          page: segment.page,
                          segmentId: segment.id,
                        });
                      }}
                      sx={{
                        borderRadius: 1.25,
                        border: (theme) =>
                          `1px solid ${
                            isActive
                              ? theme.palette.primary.main
                              : "rgba(15,23,42,0.14)"
                          }`,
                        backgroundColor: isSearchActive
                          ? "rgba(20,184,166,0.16)"
                          : isExternallyActive
                            ? "rgba(37, 99, 235, 0.14)"
                            : "rgba(15, 23, 42, 0.045)",
                        px: 1.1,
                        py: 0.95,
                        cursor: segment.page != null ? "pointer" : "default",
                        transition: "background-color 0.12s ease, border-color 0.12s ease",
                        "&:hover": {
                          backgroundColor:
                            segment.page != null
                              ? isSearchActive
                                ? "rgba(20,184,166,0.22)"
                                : isExternallyActive
                                  ? "rgba(37, 99, 235, 0.18)"
                                  : "rgba(37, 99, 235, 0.10)"
                              : "rgba(15, 23, 42, 0.045)",
                          borderColor:
                            segment.page != null
                              ? "rgba(37, 99, 235, 0.55)"
                              : "rgba(15,23,42,0.14)",
                        },
                      }}
                    >
                      <Stack spacing={0.7}>
                        <Stack
                          direction={compact ? "column" : { xs: "column", sm: "row" }}
                          spacing={0.75}
                          justifyContent="space-between"
                          alignItems={compact ? "flex-start" : { xs: "flex-start", sm: "center" }}
                        >
                          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                            <Chip label={segment.id} size="small" variant="outlined" />
                            {segment.page != null ? (
                              <Chip label={`Page ${segment.page}`} size="small" />
                            ) : (
                              <Chip
                                label="No page grounding"
                                size="small"
                                color="warning"
                                variant="outlined"
                              />
                            )}
                            {isSearchActive ? (
                              <Chip label="Search match" size="small" color="primary" />
                            ) : null}
                          </Stack>

                          <Typography variant="caption" color="text.secondary">
                            {segment.page != null ? "Jump to source" : "No source page"}
                          </Typography>
                        </Stack>

                        {isEditing ? (
                          <TextField
                            fullWidth
                            multiline
                            minRows={3}
                            value={segment.text}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) =>
                              handleChangeSegmentText(segment.id, event.target.value)
                            }
                          />
                        ) : (
                          <Typography
                            variant="body2"
                            sx={{
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                              fontFamily: 'Consolas, "Courier New", monospace',
                              fontSize: `${fontSizePx}px`,
                              lineHeight: 1.6,
                            }}
                          >
                            {segment.text || "No text available for this segment."}
                          </Typography>
                        )}
                      </Stack>
                    </Box>
                  );
                })
              )}
            </Stack>
          </Box>
        </CardContent>
      </Card>
    </Stack>
  );
}
