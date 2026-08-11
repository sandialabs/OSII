// src/features/files/pages/FilePage.tsx
import { useEffect, useMemo, useState } from "react";
import { useSearchParams, useParams } from "react-router-dom";
import {
  Alert,
  CircularProgress,
  Stack,
  Tab,
  Tabs,
} from "@mui/material";

import { useObject } from "../../../hooks/useObject";
import { useObjectTexts } from "../../../hooks/useObjectTexts";
import { useObjectPreferredText } from "../../../hooks/useObjectPreferredText";
import { toFileDetailModel } from "../../../domain/files";
import { findBestMatchingSegment } from "../../../domain/textGrounding";
import { FileHeader } from "../components/FileHeader";
import { FileTextPanel } from "../components/FileTextPanel";
import { FileSourcePanel } from "../components/FileSourcePanel";
import { FileSynthesesPanel } from "../components/FileSynthesesPanel";
import { FileEnrichmentsPanel } from "../components/FileEnrichmentsPanel";
import { FileExtractionsPanel } from "../components/FileExtractionsPanel";
import { ScopeWikiPanel } from "../components/ScopeWikiPanel";
import { FileActionBar } from "../components/FileActionBar";
import { SplitFileView } from "../components/SplitFileView";

type FileTab = "text" | "source" | "split" | "extractions" | "syntheses" | "wiki" | "enrichments";

export function FilePage() {
  const { fileId } = useParams<{ fileId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<FileTab>("split");

  const charStartValue = searchParams.get("char_start");
  const charEndValue = searchParams.get("char_end");
  const pageValue = searchParams.get("page");
  const querySegmentId = searchParams.get("segment_id");

  const charStart = charStartValue != null ? Number(charStartValue) : null;
  const charEnd = charEndValue != null ? Number(charEndValue) : null;
  const initialPage = pageValue != null ? Number(pageValue) : 1;

  const [activePage, setActivePage] = useState<number>(
    Number.isFinite(initialPage) ? initialPage : 1,
  );
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(
    querySegmentId,
  );

  const objectQuery = useObject(fileId ?? "", Boolean(fileId));
  const textsQuery = useObjectTexts(fileId ?? "", Boolean(fileId));
  const preferredTextQuery = useObjectPreferredText(fileId ?? "", Boolean(fileId));

  const detail = useMemo(
    () => (objectQuery.data ? toFileDetailModel(objectQuery.data) : null),
    [objectQuery.data],
  );

  const bestMatchSegment = useMemo(() => {
    return findBestMatchingSegment({
      segments: textsQuery.data?.segments ?? [],
      charStart: Number.isFinite(charStart) ? charStart : null,
      charEnd: Number.isFinite(charEnd) ? charEnd : null,
    });
  }, [textsQuery.data?.segments, charStart, charEnd]);

  useEffect(() => {
    const nextPage = pageValue != null ? Number(pageValue) : 1;
    if (Number.isFinite(nextPage)) {
      setActivePage(nextPage);
    }
  }, [pageValue]);

  useEffect(() => {
    setActiveSegmentId(querySegmentId);
  }, [querySegmentId]);

  useEffect(() => {
    if (!bestMatchSegment) {
      return;
    }

    const nextSegmentId = bestMatchSegment.id;
    const nextPage =
      typeof bestMatchSegment.source_origin?.page === "number"
        ? bestMatchSegment.source_origin.page
        : null;

    setActiveSegmentId(nextSegmentId);

    if (nextPage != null) {
      setActivePage(nextPage);
    }

    if (detail?.mime === "application/pdf") {
      setTab("split");
    } else {
      setTab("text");
    }
  }, [bestMatchSegment, detail?.mime]);

  if (!fileId) {
    return <Alert severity="error">Missing file ID.</Alert>;
  }

  if (objectQuery.isLoading) {
    return <CircularProgress size={24} />;
  }

  if (objectQuery.isError) {
    return (
      <Alert severity="error">
        Failed to load file.
        {objectQuery.error instanceof Error ? ` ${objectQuery.error.message}` : ""}
      </Alert>
    );
  }

  if (!objectQuery.data || !detail) {
    return <Alert severity="info">File not found.</Alert>;
  }

  const handleJumpToSource = (params: {
    page?: number | null;
    segmentId?: string | null;
  }) => {
    const nextPage =
      params.page != null && Number.isFinite(params.page) ? params.page : activePage;

    setActivePage(nextPage);
    setActiveSegmentId(params.segmentId ?? null);

    const next = new URLSearchParams(searchParams);
    next.set("page", String(nextPage));

    if (params.segmentId) {
      next.set("segment_id", params.segmentId);
    } else {
      next.delete("segment_id");
    }

    setSearchParams(next);
    setTab("split");
  };

  const handlePageChange = (nextPage: number) => {
    setActivePage(nextPage);

    const next = new URLSearchParams(searchParams);
    next.set("page", String(nextPage));
    setSearchParams(next);
  };

  return (
    <Stack spacing={3}>
      <FileHeader file={detail} />

      <Tabs
        value={tab}
        onChange={(_, nextValue: FileTab) => setTab(nextValue)}
        variant="scrollable"
        scrollButtons="auto"
      >
        <Tab label="Text" value="text" />
        <Tab label="Source" value="source" />
        <Tab label="Split View" value="split" />
        <Tab label="Extractions" value="extractions" />
        <Tab label="Syntheses" value="syntheses" />
        <Tab label="Wiki" value="wiki" />
        <Tab label="Enrichments" value="enrichments" />
      </Tabs>

      {tab === "text" && (
        <FileTextPanel
          fileId={fileId}
          supportsMarkdownRender={detail.supportsMarkdownRender}
          charStart={Number.isFinite(charStart) ? charStart : null}
          charEnd={Number.isFinite(charEnd) ? charEnd : null}
        />
      )}

      {tab === "source" && (
        <FileSourcePanel
          fileId={fileId}
          mime={detail.mime}
          page={activePage}
          onPageChange={handlePageChange}
          segments={textsQuery.data?.segments ?? []}
        />
      )}

      {tab === "split" && (
        textsQuery.isLoading || preferredTextQuery.isLoading ? (
          <CircularProgress size={24} />
        ) : textsQuery.isError ? (
          <Alert severity="error">
            Failed to load grounded text segments.
          </Alert>
        ) : preferredTextQuery.isError ? (
          <Alert severity="error">
            Failed to load preferred text.
          </Alert>
        ) : (
          <SplitFileView
            fileId={fileId}
            mime={detail.mime}
            canonicalText={preferredTextQuery.data?.text ?? ""}
            segments={textsQuery.data?.segments ?? []}
            activeSegmentId={activeSegmentId}
            page={activePage}
            onPageChange={handlePageChange}
            onJumpToSource={handleJumpToSource}
          />
        )
      )}

      {tab === "syntheses" && <FileSynthesesPanel fileId={fileId} />}

      {tab === "extractions" && <FileExtractionsPanel fileId={fileId} />}

      {tab === "wiki" && (
        <ScopeWikiPanel
          scope={{ scope_type: "object", file_id: fileId }}
          title={detail.filename}
        />
      )}

      {tab === "enrichments" && <FileEnrichmentsPanel fileId={fileId} />}

      <FileActionBar fileId={fileId} />
    </Stack>
  );
}
