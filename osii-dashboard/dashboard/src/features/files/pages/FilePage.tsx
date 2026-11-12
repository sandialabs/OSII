import { ReportPassage } from "../../research/ReportPassage";
import { useQuery } from "@tanstack/react-query";
import { getObjectExtractions, getExtractionText } from "../../../api/objects";
// src/features/files/pages/FilePage.tsx
import { useEffect, useMemo, useState } from "react";
import { useSearchParams, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  MenuItem,
  TextField,
  CircularProgress,
  Stack,
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

import { FileDetailTabs, type FileTab } from "../components/FileDetailTabs";

export function FilePage() {
  const { fileId } = useParams<{ fileId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const [tab, setTab] = useState<FileTab>(["text", "source", "split", "extractions", "syntheses", "wiki", "enrichments"].includes(requestedTab ?? "") ? requestedTab as FileTab : "split");

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
  const extractionId = searchParams.get("extraction_id") ?? "";
  const versions = useQuery({ queryKey: ["objects", fileId, "extractions"], queryFn: () => getObjectExtractions(fileId!), enabled: Boolean(fileId) });
  const versionText = useQuery({ queryKey: ["objects", fileId, "extractions", extractionId, "texts"], queryFn: () => getExtractionText(fileId!, extractionId), enabled: Boolean(fileId && extractionId) });
  const visibleSegments = extractionId ? versionText.data?.segments ?? [] : textsQuery.data?.segments ?? [];
  const visibleText = extractionId ? versionText.data?.text ?? "" : preferredTextQuery.data?.text ?? "";
  useEffect(() => {
    const value = searchParams.get("tab");
    if (["text", "source", "split", "extractions", "syntheses", "wiki", "enrichments"].includes(value ?? "")) setTab(value as FileTab);
  }, [searchParams]);
  const inspectExtraction = (id: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("extraction_id", id); next.set("tab", "split");
    for (const key of ["char_start", "char_end", "segment_id", "page"]) next.delete(key);
    setActivePage(1); setActiveSegmentId(null); setSearchParams(next); setTab("split");
  };

  const detail = useMemo(
    () => (objectQuery.data ? toFileDetailModel(objectQuery.data) : null),
    [objectQuery.data],
  );

  const bestMatchSegment = useMemo(() => {
    return findBestMatchingSegment({
      segments: visibleSegments,
      charStart: Number.isFinite(charStart) ? charStart : null,
      charEnd: Number.isFinite(charEnd) ? charEnd : null,
    });
  }, [visibleSegments, charStart, charEnd]);

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
      <Button component="a" href={`/research?file_id=${encodeURIComponent(fileId)}`} sx={{ alignSelf: "start" }}>Write research report</Button>

      <ReportPassage text={visibleText} loading={extractionId ? versionText.isLoading : preferredTextQuery.isLoading} />
      <FileDetailTabs value={tab} onChange={value => { setTab(value); const next = new URLSearchParams(searchParams); next.set("tab", value); setSearchParams(next, { replace: true }); }} />

      {["text", "source", "split"].includes(tab) && versions.data?.variants.length ? <TextField select size="small" label="Text version" slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }} value={extractionId} onChange={event => {
        const next = new URLSearchParams(searchParams);
        if (event.target.value) next.set("extraction_id", event.target.value); else next.delete("extraction_id");
        for (const key of ["char_start", "char_end", "segment_id"]) next.delete(key);
        setActiveSegmentId(null); setSearchParams(next);
      }} sx={{ maxWidth: 620 }}>
        <MenuItem value="">Primary text / corrections</MenuItem>
        {extractionId === "canonical" && <MenuItem value="canonical">Canonical extracted text</MenuItem>}
        {versions.data.variants.map(item => <MenuItem key={item.id} value={item.id}>{item.extractor.name} · {new Date(item.created_utc).toLocaleString()}{item.primary ? " · Primary" : ""}</MenuItem>)}
      </TextField> : null}
      {extractionId && versionText.isError ? <Alert severity="error">This text version could not be loaded.</Alert> : null}
      {tab === "text" && (
        <FileTextPanel
          fileId={fileId}
          textOverride={extractionId ? visibleText : undefined}
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
          segments={visibleSegments}
        />
      )}

      {tab === "split" && (
        (extractionId ? versionText.isLoading : textsQuery.isLoading || preferredTextQuery.isLoading) ? (
          <CircularProgress size={24} />
        ) : (extractionId ? versionText.isError : textsQuery.isError) ? (
          <Alert severity="error">
            Failed to load grounded text segments.
          </Alert>
        ) : !extractionId && preferredTextQuery.isError ? (
          <Alert severity="error">
            Failed to load preferred text.
          </Alert>
        ) : (
          <SplitFileView
            key={`${fileId}:${extractionId || "primary"}`}
            fileId={fileId}
            mime={detail.mime}
            readOnly={Boolean(extractionId)}
            canonicalText={visibleText}
            segments={visibleSegments}
            activeSegmentId={activeSegmentId}
            page={activePage}
            onPageChange={handlePageChange}
            onJumpToSource={handleJumpToSource}
          />
        )
      )}

      {tab === "syntheses" && <FileSynthesesPanel fileId={fileId} />}

      {tab === "extractions" && <FileExtractionsPanel fileId={fileId} onInspect={inspectExtraction} />}

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
