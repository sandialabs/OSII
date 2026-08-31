import { useEffect, useState } from "react";
import { Alert, Button, Chip, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import FindInPageOutlinedIcon from "@mui/icons-material/FindInPageOutlined";

import { getObjectExtractions, makeObjectExtractionPrimary } from "../../../api/objects";
import { getIntakeReadiness, listProcessingRuns } from "../../../api/queue";
import { useObjectExtractionJob } from "../../../hooks/useObjectExtractionJob";


export function FileExtractionsPanel({ fileId }: { fileId: string }) {
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
  const [extractionPolicy, setExtractionPolicy] = useState<"make_primary" | "save_variant">("make_primary");
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
            <Alert severity="info">No extractor is currently ready. Start or configure one in Tools &amp; services.</Alert>
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
      {(extractions.data?.variants ?? []).map((variant) => (
        <Paper key={variant.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
            <Stack spacing={0.25} minWidth={0}>
              <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography fontWeight={700}>{variant.extractor.name}</Typography>
                <Chip size="small" label={`v${variant.extractor.version}`} variant="outlined" />
                {variant.primary ? <Chip size="small" label="Primary" color="success" /> : null}
              </Stack>
              <Typography variant="caption" color="text.secondary">
                {variant.created_utc} · {variant.text_chars.toLocaleString()} characters · {variant.manifest_records} grounded segments
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>{variant.id}</Typography>
            </Stack>
            {!variant.primary ? (
              <Button
                variant="outlined"
                disabled={promote.isPending}
                onClick={() => promote.mutate(variant.id)}
              >
                Make primary
              </Button>
            ) : null}
          </Stack>
        </Paper>
      ))}
      {!extractions.isLoading && !extractions.isError && !extractions.data?.variants.length ? <Typography color="text.secondary">No extraction is available.</Typography> : null}
      {promote.isError ? <Alert severity="error">Could not change the primary extraction.</Alert> : null}
    </Stack>
  );
}
