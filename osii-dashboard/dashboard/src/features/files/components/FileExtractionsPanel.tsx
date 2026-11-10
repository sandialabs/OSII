import { useEffect, useState } from "react";
import { Alert, Box, Button, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import FindInPageOutlinedIcon from "@mui/icons-material/FindInPageOutlined";

import { getObjectExtractionArtifacts, getObjectExtractions, makeObjectExtractionPrimary } from "../../../api/objects";
import { getIntakeReadiness, listProcessingRuns } from "../../../api/queue";
import { useObjectExtractionJob } from "../../../hooks/useObjectExtractionJob";
import { ExtractionVersions } from "./ExtractionVersions";
import { ExtractionCopyEditor } from "./ExtractionCopyEditor";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";


function ExtractionArtifacts({ fileId, variantId }: { fileId: string; variantId: string }) {
  const artifacts = useQuery({
    queryKey: ["objects", fileId, "extractions", variantId, "artifacts"],
    queryFn: () => getObjectExtractionArtifacts(fileId, variantId),
  });
  if (artifacts.isLoading || artifacts.isError || !artifacts.data?.artifacts.length) return null;
  return (
    <Box component="details" sx={{ mt: 1.25 }}>
      <Typography component="summary" variant="body2" fontWeight={700} sx={{ cursor: "pointer" }}>
        Extracted data products ({artifacts.data.artifacts.length})
      </Typography>
      <Stack spacing={1.5} sx={{ mt: 1.25 }}>
        {artifacts.data.artifacts.map((artifact) => (
          <Paper key={artifact.id} variant="outlined" sx={{ p: 1.5 }}>
            <Stack spacing={1}>
              <Typography variant="caption" color="text.secondary">
                {artifact.kind} · {artifact.media_type} · {artifact.filename}
              </Typography>
              {artifact.data != null ? (
                <><EnrichmentArtifactView data={artifact.data} /><ExtractionCopyEditor fileId={fileId} variantId={variantId} artifactId={artifact.id} /></>
              ) : (
                <Alert severity="info">This extraction artifact has no inline preview.</Alert>
              )}
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Box>
  );
}


export function FileExtractionsPanel({ fileId, onInspect }: { fileId: string; onInspect?: (id: string) => void }) {
  const queryClient = useQueryClient();
  const extractionJob = useObjectExtractionJob(fileId);
  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness });
  const runs = useQuery({
    queryKey: ["processing-runs"],
    queryFn: listProcessingRuns,
    refetchInterval: (query) => query.state.data?.runs.some(
      (run) => ["queued", "pending", "running"].includes(run.status),
    ) ? 1_200 : 10_000,
  });
  const [extractorName, setExtractorName] = useState("");
  const [extractionPolicy, setExtractionPolicy] = useState<"make_primary" | "save_variant">("save_variant");
  const extractions = useQuery({
    queryKey: ["objects", fileId, "extractions"],
    queryFn: () => getObjectExtractions(fileId),
  });
  const promote = useMutation({
    mutationFn: (variantId: string) => makeObjectExtractionPrimary(fileId, variantId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "extractions"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "detail", fileId] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "texts"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "preferred-text"] }),
      ]);
    },
  });
  const extractorOptions = (readiness.data?.extractors ?? []).filter((item) => item.available);
  const selectedExtractor = extractorName
    || extractorOptions.find((item) => item.id === readiness.data?.defaults.extractor)?.id
    || extractorOptions[0]?.id
    || "";
  const queuedRunId = extractionJob.data?.id;
  const queuedRun = runs.data?.runs.find((run) => run.id === queuedRunId);
  const extractionActive = extractionJob.isPending
    || (extractionJob.isSuccess && !queuedRun)
    || ["queued", "pending", "running"].includes(queuedRun?.status ?? "");

  useEffect(() => {
    if (!queuedRun || !["done", "error"].includes(queuedRun.status)) return;
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ["objects", fileId, "extractions"] }),
      queryClient.invalidateQueries({ queryKey: ["objects", "detail", fileId] }),
      queryClient.invalidateQueries({ queryKey: ["objects", fileId, "texts"] }),
      queryClient.invalidateQueries({ queryKey: ["objects", fileId, "preferred-text"] }),
    ]);
  }, [fileId, queryClient, queuedRun?.status]);

  return (
    <Stack spacing={1.5}>
      <Alert severity="info">
        The primary extraction supplies text to browsing and future chunking, embeddings, summaries, and enrichments. Changing it preserves every previous extraction and marks dependent search artifacts stale.
      </Alert>
      <Paper variant="outlined" sx={{ p: 1.5 }}>
        <Stack spacing={1.5}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>Run another extraction</Typography>
            <Typography variant="body2" color="text.secondary">
              Choose only how this original file is read. Synthesis, embeddings, and enrichments are separate downstream operations and will not run here.
            </Typography>
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ md: "flex-start" }}>
            <TextField
              select
              size="small"
              label="Extractor"
              value={selectedExtractor}
              onChange={(event) => setExtractorName(event.target.value)}
              sx={{ minWidth: 280 }}
              helperText="Only extractors currently responding to OSII are listed."
            >
              {extractorOptions.map((item) => (
                <MenuItem key={item.id} value={item.id}>{item.display_name}</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label="After extraction"
              value={extractionPolicy}
              onChange={(event) => setExtractionPolicy(event.target.value as typeof extractionPolicy)}
              sx={{ minWidth: 330 }}
            >
              <MenuItem value="make_primary">Make primary; preserve the previous version</MenuItem>
              <MenuItem value="save_variant">Save as another version; keep current primary</MenuItem>
            </TextField>
            <Button
              variant="contained"
              startIcon={<FindInPageOutlinedIcon />}
              disabled={extractionActive || !selectedExtractor}
              onClick={() => extractionJob.mutate({
                extractor_name: selectedExtractor,
                extraction_policy: extractionPolicy,
              })}
            >
              {extractionActive ? "Extracting…" : "Run extraction"}
            </Button>
          </Stack>
          {!readiness.isLoading && !extractorOptions.length ? (
            <Alert severity="info">No extractor is currently ready. Start or configure one in Setup.</Alert>
          ) : null}
          {extractionActive ? <Alert severity="info">Extraction is queued. Existing document data remains available while it runs.</Alert> : null}
          {queuedRun?.status === "done" ? <Alert severity="success">Extraction finished and the version list was refreshed.</Alert> : null}
          {queuedRun?.status === "error" ? (
            <Alert severity="error">{queuedRun.error || queuedRun.items?.[0]?.error || "Extraction failed."}</Alert>
          ) : null}
          {extractionJob.isError ? (
            <Alert severity="error">
              {extractionJob.error instanceof Error ? extractionJob.error.message : "Could not queue extraction."}
            </Alert>
          ) : null}
        </Stack>
      </Paper>

      {extractions.isLoading ? <LinearProgress /> : null}
      {extractions.isError ? <Alert severity="error">Could not load extraction versions.</Alert> : null}
      <ExtractionVersions variants={extractions.data?.variants ?? []} onPromote={id => promote.mutate(id)} promoting={promote.isPending} onInspect={onInspect}>
        {variant => <Stack spacing={1}><ExtractionCopyEditor fileId={fileId} variantId={variant.id} /><ExtractionArtifacts fileId={fileId} variantId={variant.id} /></Stack>}
      </ExtractionVersions>
      {!extractions.isLoading && !extractions.isError && !extractions.data?.variants.length ? <Typography color="text.secondary">No extraction is available.</Typography> : null}
      {promote.isError ? <Alert severity="error">Could not change the primary extraction.</Alert> : null}
    </Stack>
  );
}
