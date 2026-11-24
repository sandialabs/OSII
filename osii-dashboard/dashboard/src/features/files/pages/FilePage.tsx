import { Link, useParams, useSearchParams } from "react-router-dom";
import { Alert, Box, Button, CircularProgress, LinearProgress, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from "@mui/material";
import ArticleOutlined from "@mui/icons-material/ArticleOutlined";
import ViewColumnOutlined from "@mui/icons-material/ViewColumnOutlined";
import { useQuery } from "@tanstack/react-query";

import { PageBreadcrumbs } from "../../../components/workbench/PageBreadcrumbs";
import { useObject } from "../../../hooks/useObject";
import { getObjectExtractions } from "../../../api/objects";
import { listProducts } from "../../../api/tools";
import { getArtifactUrl } from "../../../api/artifacts";
import { libraryProducts } from "../../../domain/libraryProducts";
import { documentProducts } from "../../../domain/documentProducts";
import { toFileDetailModel } from "../../../domain/files";
import { buildCollectionRoute } from "../../../utils/routes";
import { DerivedProductEditor } from "../components/DerivedProductEditor";
import { DocumentWorkspace, type DocumentProductGroup, type DocumentViewMode } from "../components/DocumentWorkspace";
import { DocumentReadingPane } from "../components/DocumentReadingPane";
import { ExtractionArtifacts } from "../components/ExtractionArtifacts";
import { FileActionBar } from "../components/FileActionBar";
import { FileDetails } from "../components/FileDetails";
import { FileSourcePanel } from "../components/FileSourcePanel";
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

function isKeywordProduct(product: { family: string; filename: string; title: string }) {
  return product.family === "enrichment" && (product.filename === "table--local.stats-keywords.json"
    || product.title === "Document statistics and keywords");
}

function keywordPreview(data: unknown) {
  const rows = data && typeof data === "object" && "rows" in data && Array.isArray(data.rows) ? data.rows : [];
  const keywords = rows[0]?.keywords;
  const terms = Array.isArray(keywords) ? keywords.filter((term): term is string => typeof term === "string" && Boolean(term.trim())) : [];
  return terms.length ? (
    <Box component="ul" aria-label="Keywords" sx={{ m: 0, pl: 3, "& li": { my: 0.5 } }}>
      {[...new Set(terms)].map(term => <li key={term}>{term}</li>)}
    </Box>
  ) : <Typography color="text.secondary">No keywords saved.</Typography>;
}

function FileProducts({ fileId }: { fileId: string }) {
  const [params, setParams] = useSearchParams();
  const scope = { scope_type: "object", file_id: fileId } as const;
  const object = useObject(fileId);
  const versions = useQuery({ queryKey: ["objects", fileId, "extractions", "catalog"], queryFn: () => getObjectExtractions(fileId, true), enabled: object.isSuccess });
  const saved = useQuery({ queryKey: ["products", "list", fileId], queryFn: () => listProducts(scope), enabled: object.isSuccess });

  const parents = [{ label: "Files", to: "/files" }];
  if (object.isPending || object.isError) return <Stack spacing={1.5}>
    <PageBreadcrumbs parents={parents} current="File" />
    {object.isPending ? <CircularProgress size={24} aria-label="Loading file" />
      : <Alert severity="error">Could not load file. {object.error.message}</Alert>}
  </Stack>;

  const detail = toFileDetailModel(object.data);
  const savedArtifacts = object.data.artifact_summary.artifacts;
  const products = documentProducts(saved.data?.products ?? [], object.data.enrichments);
  if (savedArtifacts.has_synthesis && !products.some(product => product.id === "synthesis:current")) {
    products.unshift({ id: "synthesis:current", family: "synthesis", filename: "current", title: "Current summary", editable: true });
  }
  const variants = versions.data?.variants ?? [];
  const primary = variants.find(version => version.primary);
  const primaryProduct = primary ? `extraction:${primary.id}` : "text";
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
  const textTarget = extractionId || page !== null || segmentId || charStart !== null || charEnd !== null;
  const mode = readingMode(params.get("view")) ?? readingMode(legacyTab) ?? (
    textTarget ? detail.mime === "application/pdf" ? "split" : "text" : "source"
  );
  const groups: DocumentProductGroup[] = [
    { label: "Source", entries: [{ id: "source", label: "Original file" }, { id: "details", label: "File details" }] },
    { label: libraryProducts.text, entries: [
      ...(!primary ? [{ id: "text", label: hasText ? "Saved text" : "No text saved" }] : []),
      ...variants.map(version => ({
        id: `extraction:${version.id}`,
        label: version.extractor.name,
        primary: version.primary,
      })),
      ...(hasCitation ? [{ id: "citation", label: "Cited passage" }] : []),
    ] },
    { label: libraryProducts.metadata, entries: [{ id: "metadata", label: "Document metadata" }] },
    { label: libraryProducts.summaries, entries: products.filter(product => product.family === "synthesis").map(product => ({ id: product.id, label: product.title })) },
    { label: libraryProducts.artifacts, entries: [
      ...products.filter(product => product.family === "enrichment").map(product => isKeywordProduct(product)
        ? { id: product.id, label: "Keywords" }
        : { id: product.id, label: product.title }),
      ...extracted,
    ] },
    { label: libraryProducts.collections, entries: [{ id: "collections", label: "Collection membership", detail: detail.collections.length.toLocaleString() }] },
  ].filter(group => group.entries.length);
  const legacyProduct = legacyTab === "syntheses" ? products.find(product => product.family === "synthesis")
    : legacyTab === "wiki" ? products.find(product => product.artifact_type === "wiki_markdown")
    : legacyTab === "enrichments" ? products.find(product => product.family === "enrichment")
    : undefined;
  const requested = params.get("product");
  const selected = (requested === "text" && !extractionId ? primaryProduct : requested) || legacyProduct?.id || (
    hasCitation ? "citation" : extractionId && extractionId !== "canonical" ? `extraction:${extractionId}`
      : legacyTab === "extractions" && variants.length ? `extraction:${variants[0].id}`
      : extractionId === "canonical" ? "text"
      : mode === "source" ? "source" : primaryProduct
  );
  const selectedEntry = groups.flatMap(group => group.entries).find(entry => entry.id === selected);
  const variantId = selected.startsWith("extraction:") ? selected.slice("extraction:".length) : undefined;
  const selectedVersion = variantId ?? ((selected === "text" || selected === "citation") ? extractionId : undefined);
  const product = products.find(item => item.id === selected);
  const keywords = product && isKeywordProduct(product);
  const extractionArtifact = extracted.find(item => item.id === selected);

  const update = (changes: Record<string, string | null>, replace = false) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    if (next.toString() !== params.toString()) setParams(next, { replace });
  };
  const selectProduct = (id: string) => {
    if (id === selected) return;
    update({
      product: id, view: mode === "split" ? "split" : id === "source" ? "source" : "text",
      tab: null, extraction_id: null, page: null, segment_id: null, char_start: null, char_end: null,
    });
  };

  const textView = selected === "text" || Boolean(variantId);
  const split = mode === "split";
  const separateSource = split && !textView && selected !== "source";
  return (
    <DocumentWorkspace
      header={<Stack spacing={1}>
        <PageBreadcrumbs parents={parents} current={detail.filename} />
        <Stack direction="row" spacing={1.5} justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="h5" component="h1" fontWeight={750} sx={{ overflowWrap: "anywhere", minWidth: 0 }}>{detail.filename}</Typography>
          <ToggleButtonGroup exclusive size="small" value={split ? "split" : "single"} aria-label="Reading layout"
            onChange={(_, layout: "single" | "split" | null) => {
              if (!layout) return;
              update({ view: layout === "split" ? "split" : selected === "source" ? "source" : "text", product: selected, tab: null }, true);
            }}>
            <ToggleButton value="single" aria-label="Single view"><Tooltip title="Single view"><ArticleOutlined fontSize="small" /></Tooltip></ToggleButton>
            <ToggleButton value="split" aria-label="Split view"><Tooltip title="Split view with original file"><ViewColumnOutlined fontSize="small" /></Tooltip></ToggleButton>
          </ToggleButtonGroup>
        </Stack>
      </Stack>}
      groups={groups} selected={selected} onSelect={selectProduct}
      sourcePane={separateSource ? <FileSourcePanel fileId={fileId} mime={detail.mime} page={page}
        compact onPageChange={value => update({ page: String(value), product: selected, view: mode }, true)} /> : undefined}
      catalogStatus={versions.isError || saved.isError
        ? <Button size="small" onClick={() => { if (versions.isError) void versions.refetch(); if (saved.isError) void saved.refetch(); }}>Retry loading products</Button>
        : versions.isPending || saved.isPending ? <LinearProgress aria-label="Loading file products" /> : null}
    >
      <Stack spacing={2} key={selected}>
        <Typography id="file-product-title" component="h2" variant="h6" fontWeight={700} sx={{ overflowWrap: "anywhere" }}>{selectedEntry?.label ?? (textView ? "Extracted text" : "Saved product")}</Typography>

        {selected === "text" && !hasText && <Typography color="text.secondary">No extracted text is saved for this file.</Typography>}
        {((textView && (hasText || variantId)) || selected === "source" || selected === "citation") && (
          <DocumentReadingPane
            key={`${selectedVersion ?? "current"}:${mode}`}
            fileId={fileId} mime={detail.mime} versionId={selectedVersion}
            mode={split && !separateSource ? "split" : selected === "source" ? "source" : "text"}
            page={page} segmentId={segmentId} charStart={charStart} charEnd={charEnd}
            showEdits={!selectedVersion || Boolean(variantId && variantId === primary?.id)}
            onPageChange={value => update({ page: String(value), product: selected, view: mode }, true)}
            onJumpToSource={target => {
              update({ product: selected, view: "split", tab: null, page: String(target.page ?? page ?? 1), segment_id: target.segmentId ?? null, char_start: null, char_end: null });
            }}
            citedPassage={selected === "citation"}
          />
        )}
        {extractionArtifact && <ExtractionArtifacts fileId={fileId} variantId={extractionArtifact.versionId} artifactId={extractionArtifact.artifactId} />}
        {selected === "metadata" && <SuggestedMetadata fileId={fileId} />}
        {selected === "details" && <Stack spacing={2}><FileDetails file={detail} meta={object.data.meta} /><FileActionBar fileId={fileId} /></Stack>}
        {selected === "collections" && <Stack spacing={1} alignItems="flex-start">
          {detail.collections.map(collection => <Button key={collection.id} component={Link} to={buildCollectionRoute(collection.id)}>{collection.name}</Button>)}
          {!detail.collections.length && <Typography color="text.secondary">This file is part of no collections.</Typography>}
        </Stack>}
        {product?.editable && <DerivedProductEditor scope={scope} filename={product.filename} family={product.family === "synthesis" ? "synthesis" : "enrichment"}
          preview={keywords ? keywordPreview : undefined} />}
        {product?.relpath && !keywords && <Button component="a" download href={getArtifactUrl(product.relpath)} sx={{ alignSelf: "flex-start" }}>Download saved artifact</Button>}
        {selected !== "source" && selected !== "citation" && !selectedEntry && !textView && !saved.isPending && (
          <Alert severity="info">This saved product is unavailable.</Alert>
        )}
      </Stack>
    </DocumentWorkspace>
  );
}
