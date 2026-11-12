import { MathpixText } from "../../../components/text/MathpixText";
// src/features/files/components/FileTextPanel.tsx
import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  ButtonGroup,
  Card,
  CardContent,
  Stack,
  Typography,
} from "@mui/material";

import { useObjectPreferredText } from "../../../hooks/useObjectPreferredText";
import { useObjectTextSpanContext } from "../../../hooks/useObjectTextSpanContext";

type TextRenderMode = "raw" | "rendered";

type FileTextPanelProps = {
  fileId: string;
  textOverride?: string;
  charStart?: number | null;
  charEnd?: number | null;
};

export function FileTextPanel({
  fileId,
  textOverride,
  charStart = null,
  charEnd = null,
}: FileTextPanelProps) {
  const [renderMode, setRenderMode] = useState<TextRenderMode>("rendered");
  const textQuery = useObjectPreferredText(fileId, textOverride === undefined);
  const contextQuery = useObjectTextSpanContext(
    {
      fileId,
      charStart,
      charEnd,
      contextChars: 180,
    },
    textOverride === undefined && charStart != null && charEnd != null,
  );

  const content = textOverride ?? textQuery.data?.text ?? "";
  const canRenderMarkdown =
    Boolean(content.trim());

  const highlightedBlock = useMemo(() => {
    if (!contextQuery.data) {
      return null;
    }

    return {
      before: contextQuery.data.before_text,
      match: contextQuery.data.match_text,
      after: contextQuery.data.after_text,
    };
  }, [contextQuery.data]);

  if (textOverride === undefined && textQuery.isLoading) {
    return <Typography>Loading preferred text…</Typography>;
  }

  if (textOverride === undefined && textQuery.isError) {
    return <Alert severity="warning">Failed to load preferred text.</Alert>;
  }

  if ((!textQuery.data && textOverride === undefined) || !content) {
    return (
      <Alert severity="info">
        No preferred text is available for this file.
      </Alert>
    );
  }

  const preferredText = textQuery.data;

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={2}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", md: "center" }}
      >
        <Stack spacing={0.25}>
          <Typography variant="subtitle1" fontWeight={600}>
            {textOverride === undefined ? "Preferred text" : "Extracted text version"}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {textOverride === undefined ? `Representation: ${preferredText?.representation} · ${preferredText?.kind}` : "Saved extraction · read only"}
          </Typography>
        </Stack>

        <ButtonGroup size="small" variant="outlined">
          <Button
            variant={renderMode === "raw" ? "contained" : "outlined"}
            onClick={() => setRenderMode("raw")}
          >
            Plain text
          </Button>
          <Button
            variant={renderMode === "rendered" ? "contained" : "outlined"}
            onClick={() => setRenderMode("rendered")}
            disabled={!canRenderMarkdown}
          >
            Mathpix Markdown
          </Button>
        </ButtonGroup>
      </Stack>

      {charStart != null && charEnd != null ? (
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="subtitle2" fontWeight={600}>
                Grounded Match
              </Typography>

              {contextQuery.isLoading ? (
                <Typography variant="body2" color="text.secondary">
                  Loading match context…
                </Typography>
              ) : contextQuery.isError ? (
                <Alert severity="warning">Failed to load grounded text context.</Alert>
              ) : highlightedBlock ? (
                <Box
                  sx={{
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    fontFamily: 'Consolas, "Courier New", monospace',
                    fontSize: "0.85rem",
                    lineHeight: 1.55,
                  }}
                >
                  <span>{highlightedBlock.before}</span>
                  <Box
                    component="span"
                    sx={{
                      backgroundColor: "rgba(245, 158, 11, 0.28)",
                      borderRadius: "3px",
                      px: "1px",
                    }}
                  >
                    {highlightedBlock.match}
                  </Box>
                  <span>{highlightedBlock.after}</span>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No grounded match context available.
                </Typography>
              )}
            </Stack>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent sx={{ p: 0 }}>
          <Box
            sx={{
              maxHeight: "68vh",
              overflowY: "auto",
              overflowX: "hidden",
              px: 2,
              py: 1.5,
            }}
          >
            <MathpixText text={content} controls={false} mode={renderMode === "rendered" ? "rendered" : "plain"} />
          </Box>
        </CardContent>
      </Card>
    </Stack>
  );
}