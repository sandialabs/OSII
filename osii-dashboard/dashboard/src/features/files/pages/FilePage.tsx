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
  TextField, Accordion, AccordionSummary, AccordionDetails, Typography,
  CircularProgress,
  Stack,
} from "@mui/material";

import { useObject } from "../../../hooks/useObject";
import { useObjectTexts } from "../../../hooks/useObjectTexts";
import { useObjectPreferredText } from "../../../hooks/useObjectPreferredText";
import { toFileDetailModel } from "../../../domain/files";
import { findBestMatchingSegment } from "../../../domain/textGrounding";
import { FileHeader } from "../components/FileHeader";
import { GroundedSegmentEditor } from "../components/GroundedSegmentEditor";
import { DocumentWorkspace, type DocumentViewMode, type SavedDocumentPanel } from "../components/DocumentWorkspace";
import { useScopeEnrichments } from "../../../hooks/useScopeEnrichments";
import { DerivedProductEditor } from "../components/DerivedProductEditor";
import { ExpandMore } from "@mui/icons-material";
import { FileSourcePanel } from "../components/FileSourcePanel";
import { ExtractionArtifacts } from "../components/FileExtractionsPanel";
import { FileEnrichmentsPanel } from "../components/FileEnrichmentsPanel";
import { FileSynthesesPanel } from "../components/FileSynthesesPanel";
import { FileActionBar } from "../components/FileActionBar";
import { SplitFileView } from "../components/SplitFileView";

type FileTab = DocumentViewMode;

export function FilePage() {
  const { fileId } = useParams<{ fileId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("view") || searchParams.get("tab");
  const [tab, setTab] = useState<FileTab>(["text", "source", "split"].includes(requestedTab ?? "") ? requestedTab as FileTab : "split");

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

  const enrichments = useScopeEnrichments({scope_type:"object",file_id:fileId ?? ""},Boolean(fileId));
  const savedProducts = useQuery({queryKey:["document-products",fileId],queryFn:()=>import("../../../api/client").then(({apiJson})=>apiJson<{products:{filename:string;family:string;title:string;artifact_type?:string}[]}>("/api/products/list",{method:"POST",json:{scope_type:"object",file_id:fileId}})),enabled:Boolean(fileId)});
  const objectQuery = useObject(fileId ?? "", Boolean(fileId));
  const textsQuery = useObjectTexts(fileId ?? "", Boolean(fileId));
  const preferredTextQuery = useObjectPreferredText(fileId ?? "", Boolean(fileId));
  const [editing,setEditing]=useState(false);
  const extractionId = searchParams.get("extraction_id") ?? "";
  const versions = useQuery({ queryKey: ["objects", fileId, "extractions"], queryFn: () => getObjectExtractions(fileId!), enabled: Boolean(fileId) });
  const versionText = useQuery({ queryKey: ["objects", fileId, "extractions", extractionId, "texts"], queryFn: () => getExtractionText(fileId!, extractionId), enabled: Boolean(fileId && extractionId) });
  const visibleSegments = extractionId ? versionText.data?.segments ?? [] : textsQuery.data?.segments ?? [];
  const visibleText = extractionId ? versionText.data?.text ?? "" : preferredTextQuery.data?.text ?? "";
  useEffect(() => {
    const value = searchParams.get("view") || searchParams.get("tab");
    if (["text", "source", "split"].includes(value ?? "")) setTab(value as FileTab);
  }, [searchParams]);
  const inspectExtraction = (id: string) => {
    if(editing && !window.confirm("Discard unsaved text edits?"))return;
    setEditing(false);
    const next = new URLSearchParams(searchParams);
    next.set("extraction_id", id); next.set("view", "split"); next.delete("tab");
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
    next.set("page", String(nextPage)); next.set("view", "split"); next.delete("tab");

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

  const textControls=<Accordion disableGutters variant="outlined" slotProps={{transition:{unmountOnExit:true}}}><AccordionSummary expandIcon={<ExpandMore/>}><Typography variant="body2">Text options</Typography></AccordionSummary><AccordionDetails>{versions.data?.variants.length ? <TextField select disabled={editing} size="small" label="Text version" slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }} value={extractionId} onChange={event => {
        const next = new URLSearchParams(searchParams);
        if (event.target.value) next.set("extraction_id", event.target.value); else next.delete("extraction_id");
        for (const key of ["char_start", "char_end", "segment_id"]) next.delete(key);
        setActiveSegmentId(null); setSearchParams(next);
      }} sx={{ maxWidth: 620 }}>
        <MenuItem value="">Primary text / corrections</MenuItem>
        {extractionId === "canonical" && <MenuItem value="canonical">Canonical extracted text</MenuItem>}
        {versions.data.variants.map(item => <MenuItem key={item.id} value={item.id}>{item.extractor.name} · {new Date(item.created_utc).toLocaleString()}{item.primary ? " · Primary" : ""}</MenuItem>)}
      </TextField> : null}</AccordionDetails></Accordion>;
  const panels:SavedDocumentPanel[]=[];
  if(detail.hasSynthesis)panels.push({id:"summary",label:"Summary",description:"A short account of this document."});
  const named=(enrichments.data?.enrichments ?? []).filter(entry=>entry.kind==="file"&&!entry.name.endsWith(".meta.json"));
  for(const entry of named)panels.push({id:"saved:"+entry.name,label:entry.kind==="file"&&entry.artifact_type==="wiki_markdown"?"Wiki":(entry.kind==="file"?entry.title:undefined)||entry.name,description:entry.kind==="file"&&entry.artifact_type==="wiki_markdown"?"A structured reference organized by topic.":"Saved document data."});
  for(const item of savedProducts.data?.products ?? [])if(!named.some(entry=>entry.name===item.filename))panels.push({id:"product:"+item.filename,label:item.title,description:item.family==="synthesis"?"A short account of the document.":"Saved document data."});
  if(enrichments.data?.enrichments.some(entry=>entry.kind==="bundle"))panels.push({id:"enrichments",label:"Other saved data"});
  if(versions.data?.variants.length)panels.push({id:"versions",label:"Text versions"});
  panels.push({id:"details",label:"File details"});
  if(searchParams.has("report_source"))panels.push({id:"citation",label:"Cited passage"});
  return <DocumentWorkspace mode={tab} onMode={value=>{if(editing && !window.confirm("Discard unsaved text edits?"))return;setEditing(false);setTab(value);const next=new URLSearchParams(searchParams);next.set("view",value);next.delete("tab");setSearchParams(next,{replace:true});}}
    header={<Typography fontWeight={700} sx={{overflowWrap:"anywhere"}}>{detail.filename}</Typography>}
    panels={panels} initialPanel={searchParams.get("tab")==="extractions"?"versions":searchParams.get("tab")==="syntheses"?"summary":searchParams.get("tab")==="wiki"?panels.find(panel=>panel.label==="Wiki")?.id:searchParams.get("tab")==="enrichments"?panels.find(panel=>panel.id.startsWith("saved:")||panel.id==="enrichments")?.id:undefined} renderPanel={id=>id==="enrichments"?<FileEnrichmentsPanel fileId={fileId} showActions={false}/>:id==="citation"?<ReportPassage text={visibleText} loading={extractionId?versionText.isLoading:preferredTextQuery.isLoading}/>:id==="summary"?<FileSynthesesPanel fileId={fileId} showActions={false}/>:id==="details"?<Stack spacing={2}><FileHeader file={detail}/><FileActionBar fileId={fileId}/></Stack>:id==="versions"?<Stack spacing={1}>{versions.data?.variants.map(item=><Accordion key={item.id} disableGutters variant="outlined" slotProps={{transition:{unmountOnExit:true}}}><AccordionSummary expandIcon={<ExpandMore/>}><Typography variant="body2">{item.primary?"Current text":item.extractor.name}</Typography></AccordionSummary><AccordionDetails><Button onClick={()=>inspectExtraction(item.id)}>Read this text</Button><ExtractionArtifacts fileId={fileId} variantId={item.id}/></AccordionDetails></Accordion>)}</Stack>:id.startsWith("saved:")?<DerivedProductEditor scope={{scope_type:"object",file_id:fileId}} filename={id.slice(6)}/>:<DerivedProductEditor scope={{scope_type:"object",file_id:fileId}} filename={id.slice(8)} family={savedProducts.data?.products.find(item=>item.filename===id.slice(8))?.family as "synthesis"|"enrichment"}/> }>
    <Stack spacing={1.5}>
      {extractionId && versionText.isError ? <Alert severity="error">This text version could not be loaded.</Alert> : null}
      {tab === "text" && <GroundedSegmentEditor key={extractionId||"primary"} fileId={fileId} readOnly={Boolean(extractionId)} canonicalText={visibleText} segments={visibleSegments} onEditingChange={setEditing} controls={textControls} onJumpToSource={handleJumpToSource} />}

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
            textControls={textControls}
            mime={detail.mime}
            readOnly={Boolean(extractionId)}
            onEditingChange={setEditing}
            canonicalText={visibleText}
            segments={visibleSegments}
            activeSegmentId={activeSegmentId}
            page={activePage}
            onPageChange={handlePageChange}
            onJumpToSource={handleJumpToSource}
          />
        )
      )}

    </Stack></DocumentWorkspace>;
}
