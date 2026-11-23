import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, CircularProgress, LinearProgress, Stack, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import DocumentScannerOutlined from "@mui/icons-material/DocumentScannerOutlined";
import { useQuery } from "@tanstack/react-query";

import { useObject } from "../../../hooks/useObject";
import { getObjectExtractions } from "../../../api/objects";
import { listProducts } from "../../../api/tools";
import { getArtifactUrl } from "../../../api/artifacts";
import { libraryProducts } from "../../../domain/libraryProducts";
import { documentProducts } from "../../../domain/documentProducts";
import { toFileDetailModel } from "../../../domain/files";
import { buildCollectionRoute } from "../../../utils/routes";
import { buildOcrRoute } from "../../ocr/routes";
import { DerivedProductEditor } from "../components/DerivedProductEditor";
import { DocumentWorkspace, type DocumentProductGroup, type DocumentViewMode } from "../components/DocumentWorkspace";
import { DocumentReadingPane } from "../components/DocumentReadingPane";
import { ExtractionArtifacts } from "../components/ExtractionArtifacts";
import { FileActionBar } from "../components/FileActionBar";
import { FileHeader } from "../components/FileHeader";
import { SuggestedMetadata } from "../components/SuggestedMetadata";

const readingModes = ["source", "split", "text"] as const;
function readingMode(value: string | null): DocumentViewMode | undefined {
  return readingModes.find(mode => mode === value);
}

function numberParam(params: URLSearchParams, name: string) {
  const value = params.get(name);
  return value !== null && Number.isFinite(Number(value)) ? Number(value) : null;
}

export function FilePage() {
  const { fileId } = useParams<{ fileId: string }>();
  return fileId ? <FileProducts key={fileId} fileId={fileId} /> : <Alert severity="error">Missing file ID.</Alert>;
}

function FileProducts({ fileId }: { fileId: string }) {
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState(false);
  const scope = { scope_type: "object", file_id: fileId } as const;
  const object = useObject(fileId);
  const versions = useQuery({ queryKey: ["objects", fileId, "extractions", "catalog"], queryFn: () => getObjectExtractions(fileId, true), enabled: object.isSuccess });
  const saved = useQuery({ queryKey: ["products", "list", fileId], queryFn: () => listProducts(scope), enabled: object.isSuccess });

  if (object.isPending) return <CircularProgress size={24} aria-label="Loading file" />;
  if (object.isError) return <Alert severity="error">Could not load file. {object.error.message}</Alert>;

  const detail = toFileDetailModel(object.data);
  const savedArtifacts = object.data.artifact_summary.artifacts;
  const products = documentProducts(saved.data?.products ?? [], object.data.enrichments);
  if (savedArtifacts.has_synthesis && !products.some(product => product.id === "synthesis:current")) {
    products.unshift({ id: "synthesis:current", family: "synthesis", filename: "current", title: "Current summary", editable: true });
  }
  const variants = versions.data?.variants ?? [];
  const extracted = variants.flatMap(version => (version.artifacts ?? []).map(artifact => ({
    id: `extraction-artifact:${JSON.stringify([version.id, artifact.id])}`,
    label: artifact.filename,
    detail: version.extractor.name,
    versionId: version.id,
    artifactId: artifact.id,
  })));
  const hasText = savedArtifacts.has_extraction || savedArtifacts.text_representations.some(item => item.exists);
  const extractionId = params.get("extraction_id") || undefined;
  const legacyTab = params.get("tab");
  const charStart = numberParam(params, "char_start");
  const charEnd = numberParam(params, "char_end");
  const page = numberParam(params, "page");
  const segmentId = params.get("segment_id");
  const hasCitation = params.has("report_source");
  const mode = readingMode(params.get("view")) ?? readingMode(legacyTab) ?? (
    detail.mime === "application/pdf" && (extractionId || page || segmentId || charStart !== null) ? "split" : "text"
  );
  const groups: DocumentProductGroup[] = [
    { label: "Source", entries: [{ id: "source", label: "Original file" }, { id: "details", label: "File details" }] },
    { label: libraryProducts.text, entries: [
      { id: "text", label: "Current text", detail: hasText ? undefined : "No text saved" },
      ...variants.map(version => ({
        id: `extraction:${version.id}`,
        label: version.extractor.name,
        detail: new Date(version.created_utc).toLocaleString() + (version.primary ? " · Primary" : ""),
      })),
      ...(hasCitation ? [{ id: "citation", label: "Cited passage" }] : []),
    ] },
    { label: libraryProducts.metadata, entries: [{ id: "metadata", label: "Document metadata" }] },
    { label: libraryProducts.summaries, entries: products.filter(product => product.family === "synthesis").map(product => ({ id: product.id, label: product.title })) },
    { label: libraryProducts.artifacts, entries: [
      ...products.filter(product => product.family === "enrichment").map(product => ({ id: product.id, label: product.title, detail: product.artifact_type?.replace(/_/g, " ") ?? undefined })),
      ...extracted,
    ] },
    { label: libraryProducts.collections, entries: [{ id: "collections", label: "Collection membership", detail: detail.collections.length.toLocaleString() }] },
  ].filter(group => group.entries.length);
  const legacyProduct = legacyTab === "syntheses" ? products.find(product => product.family === "synthesis")
    : legacyTab === "wiki" ? products.find(product => product.artifact_type === "wiki_markdown")
    : legacyTab === "enrichments" ? products.find(product => product.family === "enrichment")
    : undefined;
  const selected = params.get("product") || legacyProduct?.id || (
    hasCitation ? "citation" : extractionId && extractionId !== "canonical" ? `extraction:${extractionId}`
      : legacyTab === "extractions" && variants.length ? `extraction:${variants[0].id}`
      : mode === "source" || (!hasText && !readingMode(params.get("view")) && !readingMode(legacyTab)) ? "source" : "text"
  );
  const selectedEntry = groups.flatMap(group => group.entries).find(entry => entry.id === selected);
  const variantId = selected.startsWith("extraction:") ? selected.slice("extraction:".length) : undefined;
  const selectedVersion = variantId ?? ((selected === "text" || selected === "citation") ? extractionId : undefined);
  const product = products.find(item => item.id === selected);
  const extractionArtifact = extracted.find(item => item.id === selected);

  const update = (changes: Record<string, string | null>, replace = false) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    if (next.toString() !== params.toString()) setParams(next, { replace });
  };
  const canLeaveText = () => !editing || window.confirm("Discard unsaved text edits?");
  const selectProduct = (id: string) => {
    if (id === selected || !canLeaveText()) return;
    setEditing(false);
    update({
      product: id, view: id === "source" ? "source" : id.startsWith("extraction:") ? "split" : "text",
      tab: null, extraction_id: null, page: null, segment_id: null, char_start: null, char_end: null,
    });
  };

  const textView = selected === "text" || Boolean(variantId);
  const ocrPath = buildOcrRoute(fileId);
  return (
    <DocumentWorkspace
      header={<Stack direction="row" spacing={1.5} justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap>
        <Stack minWidth={0}>
          <Typography variant="h5" component="h1" fontWeight={750} sx={{ overflowWrap: "anywhere" }}>{detail.filename}</Typography>
          <Typography variant="caption" color="text.secondary">One file · Review saved products</Typography>
        </Stack>
        <Button component={Link} to={ocrPath} variant="outlined" startIcon={<DocumentScannerOutlined />}
          onClick={event => { if (!canLeaveText()) event.preventDefault(); }}>Open OCR Workbench</Button>
      </Stack>}
      groups={groups} selected={selected} onSelect={selectProduct}
      catalogStatus={versions.isError || saved.isError
        ? <Button size="small" onClick={() => { if (versions.isError) void versions.refetch(); if (saved.isError) void saved.refetch(); }}>Retry loading products</Button>
        : versions.isPending || saved.isPending ? <LinearProgress aria-label="Loading file products" /> : null}
    >
      <Stack spacing={2} key={selected}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1} flexWrap="wrap" useFlexGap>
          <Typography id="file-product-title" component="h2" variant="h6" fontWeight={700} sx={{ overflowWrap: "anywhere" }}>{selectedEntry?.label ?? "Saved product"}</Typography>
          {textView && <ToggleButtonGroup exclusive size="small" value={mode === "source" ? "text" : mode} aria-label="Reading layout"
            onChange={(_, view: DocumentViewMode | null) => {
              if (!view || !canLeaveText()) return;
              setEditing(false);
              update({ view, product: selected, tab: null }, true);
            }}>
            <ToggleButton value="text">Text</ToggleButton>
            <ToggleButton value="split">Source and text</ToggleButton>
          </ToggleButtonGroup>}
        </Stack>

        {(textView || selected === "source" || selected === "citation") && (
          <DocumentReadingPane
            key={`${selectedVersion ?? "current"}:${mode}`}
            fileId={fileId} mime={detail.mime} versionId={selectedVersion}
            mode={selected === "source" ? "source" : mode === "source" ? "text" : mode}
            page={page} segmentId={segmentId} charStart={charStart} charEnd={charEnd}
            onPageChange={value => update({ page: String(value) }, true)}
            onJumpToSource={target => {
              if (mode !== "split") {
                if (!canLeaveText()) return;
                setEditing(false);
              }
              update({ product: selected, view: "split", tab: null, page: String(target.page ?? page ?? 1), segment_id: target.segmentId ?? null, char_start: null, char_end: null });
            }}
            onEditingChange={setEditing}
            citedPassage={selected === "citation"}
          />
        )}
        {variantId && <ExtractionArtifacts fileId={fileId} variantId={variantId} />}
        {extractionArtifact && <ExtractionArtifacts fileId={fileId} variantId={extractionArtifact.versionId} artifactId={extractionArtifact.artifactId} />}
        {selected === "metadata" && <SuggestedMetadata fileId={fileId} />}
        {selected === "details" && <Stack spacing={2}><FileHeader file={detail} /><FileActionBar fileId={fileId} /></Stack>}
        {selected === "collections" && <Stack spacing={1} alignItems="flex-start">
          {detail.collections.map(collection => <Button key={collection.id} component={Link} to={buildCollectionRoute(collection.id)}>{collection.name}</Button>)}
          {!detail.collections.length && <Typography color="text.secondary">This file has no collections.</Typography>}
          <Button component={Link} to={`/tools/collections?file_id=${encodeURIComponent(fileId)}`}>Add to a collection</Button>
        </Stack>}
        {product?.editable && <DerivedProductEditor scope={scope} filename={product.filename} family={product.family === "synthesis" ? "synthesis" : "enrichment"} />}
        {product?.relpath && <Button component="a" download href={getArtifactUrl(product.relpath)} sx={{ alignSelf: "flex-start" }}>Download saved artifact</Button>}
        {selected !== "source" && selected !== "citation" && !selectedEntry && !variantId && !saved.isPending && (
          <Alert severity="info">This saved product is unavailable.</Alert>
        )}
      </Stack>
    </DocumentWorkspace>
  );
}
