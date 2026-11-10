import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { getToolCatalog } from "../../api/tools";
import { getScopeOverview } from "../../api/scopes";
import { listProcessingRuns } from "../../api/queue";
import type { ScopeDescribeRequest } from "../../api/types";
import { useEnrichmentJob } from "../../hooks/useEnrichmentJob";
import { useScopeKeywordSuggestions } from "../../hooks/useScopeKeywordSuggestions";

function sizeLabel(value: number | null): string {
  if (value === null) return "Not recorded";
  if (value < 1024) return `${Math.round(value)} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

export function ScopeOverviewPanel({ scope }: { scope: ScopeDescribeRequest }) {
  const navigate = useNavigate();
  const [dateKind, setDateKind] = useState<"created" | "modified">("created");
  const overview = useQuery({
    queryKey: ["scopes", "overview", scope],
    queryFn: () => getScopeOverview(scope),
    refetchInterval: 15_000,
    staleTime: 5_000,
  });
  const topics = useScopeKeywordSuggestions(scope);
  const tools = useQuery({ queryKey: ["tool-catalog"], queryFn: getToolCatalog, staleTime: 30_000 });
  const keywordMethod = tools.data?.methods.find(method => method.id === "noun_adjective_ngrams" && method.scopes.includes(scope.scope_type) && !method.configuration_error)
    ?? tools.data?.methods.find(method => method.id === "local.stats-keywords" && method.scopes.includes(scope.scope_type) && !method.configuration_error);
  const enrichment = useEnrichmentJob();
  const runs = useQuery({
    queryKey: ["processing-runs"],
    queryFn: listProcessingRuns,
    refetchInterval: (query) =>
      query.state.data?.runs.some((run) =>
        ["queued", "pending", "running"].includes(run.status),
      )
        ? 1_200
        : 10_000,
  });
  const topicJob = runs.data?.runs.find(
    (run) => run.id === enrichment.data?.run_id,
  );
  const topicRunning =
    enrichment.isPending ||
    (enrichment.isSuccess && !topicJob) ||
    Boolean(
      topicJob && ["queued", "pending", "running"].includes(topicJob.status),
    );
  const data = overview.data;
  const dates = data?.dates[dateKind];
  const maxCount = Math.max(
    1,
    ...(dates?.buckets.map((bucket) => bucket.count) ?? []),
  );
  const typeRows = data?.file_types.slice(0, 6) ?? [];
  const otherTypes = (data?.file_types.slice(6) ?? []).reduce(
    (sum, item) => sum + item.count,
    0,
  );
  if (otherTypes) typeRows.push({ label: "Other formats", count: otherTypes });
  const searchTopic = (topic: string) => {
    const params = new URLSearchParams({ q: topic, mode: "lexical", ...scope });
    navigate(`/search?${params.toString()}`);
  };
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, sm: 2.5 }, borderRadius: 2 }}>
      <Stack spacing={2}>
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="center"
          spacing={1}
        >
          <Typography variant="h6" fontWeight={700}>
            {scope.scope_type === "collection" ? "Collection" : "Library"} at a
            glance
          </Typography>
          <Button
            size="small"
            onClick={() => void overview.refetch()}
            disabled={overview.isFetching}
          >
            Refresh
          </Button>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Recorded documents in OSII—not a live inventory of unprocessed files
          in your source folder.
        </Typography>
        {overview.isLoading ? (
          <LinearProgress aria-label="Loading collection overview" />
        ) : null}
        {overview.isError ? (
          <Alert severity="error">
            Could not load the overview.{" "}
            {overview.error instanceof Error
              ? overview.error.message
              : "Try Refresh."}
          </Alert>
        ) : null}
        {data ? (
          <>
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: {
                  xs: "repeat(2, 1fr)",
                  md: "repeat(4, 1fr)",
                },
                gap: 2,
              }}
            >
              {[
                ["Files", data.file_count.toLocaleString()],
                [
                  "Recorded size",
                  sizeLabel(
                    data.size_known_count ? data.total_size_bytes : null,
                  ),
                ],
                ["Average file size", sizeLabel(data.average_size_bytes)],
                [
                  "Saved text",
                  `${data.processing.text_count.toLocaleString()} / ${data.file_count.toLocaleString()}`,
                ],
              ].map(([label, value]) => (
                <Stack key={label} spacing={0.25}>
                  <Typography variant="caption" color="text.secondary">
                    {label}
                  </Typography>
                  <Typography variant="h5" fontWeight={700}>
                    {value}
                  </Typography>
                </Stack>
              ))}
            </Box>
            <Typography variant="caption" color="text.secondary">
              Sizes recorded for {data.size_known_count} of {data.file_count}{" "}
              files; averages exclude missing sizes.{" "}
              {data.processing.indexed_count} files have current semantic
              vectors for the selected model; {data.processing.synthesis_count}{" "}
              have summaries and {data.processing.enrichment_count} have
              enrichments.
            </Typography>
            {data.file_count === 0 ? (
              <Typography variant="body2" color="text.secondary">
                This scope is empty. Read documents in Intake, then this
                overview will fill in automatically.
              </Typography>
            ) : null}
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
                gap: 3,
                borderTop: "1px solid",
                borderColor: "divider",
                pt: 2,
              }}
            >
              <Stack spacing={1}>
                <Typography variant="subtitle2" fontWeight={700}>
                  File formats
                </Typography>
                {typeRows.map((item) => (
                  <Stack
                    key={item.label}
                    direction="row"
                    alignItems="center"
                    spacing={1}
                  >
                    <Typography
                      variant="caption"
                      sx={{ width: 140, flexShrink: 0 }}
                    >
                      {item.label}
                    </Typography>
                    <Box
                      sx={{
                        height: 8,
                        flex: 1,
                        bgcolor: "action.hover",
                        borderRadius: 1,
                      }}
                    >
                      <Box
                        sx={{
                          height: "100%",
                          width: `${(item.count / Math.max(1, data.file_count)) * 100}%`,
                          bgcolor: "secondary.main",
                          borderRadius: 1,
                        }}
                      />
                    </Box>
                    <Typography variant="caption">{item.count}</Typography>
                  </Stack>
                ))}
              </Stack>
              <Stack spacing={1}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Document timeline
                </Typography>
                <Tabs
                  value={dateKind}
                  onChange={(_, value: "created" | "modified") =>
                    setDateKind(value)
                  }
                  aria-label="Timeline date source"
                >
                  <Tab value="created" label="Creation" />
                  <Tab value="modified" label="Last modified" />
                </Tabs>
                {dates?.buckets.length ? (
                  <Box
                    role="img"
                    aria-label={`${dateKind === "created" ? "Filesystem creation" : "Last modification"} histogram: ${dates.buckets.map((bucket) => `${bucket.label}: ${bucket.count} files`).join(", ")}`}
                    sx={{
                      display: "flex",
                      gap: 0.5,
                      minHeight: 130,
                      alignItems: "flex-end",
                    }}
                  >
                    {dates.buckets.map((bucket) => (
                      <Stack
                        key={bucket.label}
                        alignItems="center"
                        justifyContent="flex-end"
                        spacing={0.5}
                        sx={{ flex: 1, minWidth: 0 }}
                      >
                        <Typography variant="caption">
                          {bucket.count}
                        </Typography>
                        <Box
                          sx={{
                            bgcolor: "secondary.main",
                            width: "80%",
                            minHeight: 2,
                            height: (bucket.count / maxCount) * 75,
                            borderRadius: "3px 3px 0 0",
                          }}
                        />
                        <Typography
                          variant="caption"
                          sx={{
                            fontSize: "0.65rem",
                            overflowWrap: "anywhere",
                            textAlign: "center",
                          }}
                        >
                          {bucket.label}
                        </Typography>
                      </Stack>
                    ))}
                  </Box>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No{" "}
                    {dateKind === "created"
                      ? "filesystem creation"
                      : "modification"}{" "}
                    dates were recorded.{" "}
                    {dateKind === "created"
                      ? "Try Last modified for the available timeline."
                      : "Dates will appear when source metadata is available."}
                  </Typography>
                )}
                <Typography variant="caption" color="text.secondary">
                  {dates?.recorded_count ?? 0} recorded ·{" "}
                  {dates?.missing_count ?? data.file_count} missing.{" "}
                  {dateKind === "created"
                    ? "Filesystem birth time, not an author's document date; copying files can change it. No ctime or intake-date substitution."
                    : "Source-file modification times recorded at extraction."}
                </Typography>
              </Stack>
            </Box>
            <Stack
              spacing={1}
              sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2 }}
            >
              <Stack
                direction={{ xs: "column", sm: "row" }}
                justifyContent="space-between"
                spacing={1}
              >
                <Stack spacing={0.25}>
                  <Typography variant="subtitle2" fontWeight={700}>
                    Recurring topics · statistical clues
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {keywordMethod?.id === "noun_adjective_ngrams" ? "Heuristically ranked English noun/adjective phrases" : "Frequent keywords from saved text"} in this scope. These are statistical clues, not verified themes. Select a term to search its sources.
                  </Typography>
                </Stack>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={data.permissions?.run === false || tools.data?.permissions?.run === false || !keywordMethod || !data.processing.text_count || topicRunning}
                  onClick={() =>
                    enrichment.mutate(
                      {
                        enricher_name: keywordMethod!.id,
                        scope,
                        enricher_config: { top_k: 20 },
                      },
                      {
                        onSuccess: () => {
                          void runs.refetch();
                        },
                      },
                    )
                  }
                >
                  {topicRunning
                    ? "Generating…"
                    : topics.hasSnapshot
                      ? "Refresh topics"
                      : "Reveal topics"}
                </Button>
              </Stack>
              <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                {topics.keywords.map((topic) => (
                  <Chip
                    key={topic}
                    label={topic}
                    variant="outlined"
                    onClick={() => searchTopic(topic)}
                  />
                ))}
              </Stack>
              {!topics.keywords.length ? (
                <Typography variant="body2" color="text.secondary">
                  {topics.isLoading
                    ? "Loading saved topic clues…"
                    : "No topic snapshot yet. Reveal topics uses the bundled, model-free keyword method."}
                </Typography>
              ) : null}
              {enrichment.isError ||
              topics.isError ||
              topicJob?.status === "error" ? (
                <Alert severity="warning">
                  Topic clues could not be loaded or generated.{" "}
                  {topicJob?.error} File statistics are still available.
                </Alert>
              ) : null}
              {enrichment.isSuccess && topicJob?.status !== "error" ? (
                <Typography
                  variant="caption"
                  color={
                    topicJob?.status === "done"
                      ? "success.main"
                      : "text.secondary"
                  }
                >
                  {topicJob?.status === "done"
                    ? "Topic snapshot saved for this scope."
                    : "Topic generation started. The saved snapshot appears when processing finishes."}
                </Typography>
              ) : null}
            </Stack>
            {data.warnings.length || data.missing_metadata_count ? (
              <Alert severity="warning">
                Metadata is incomplete for some documents.{" "}
                {data.missing_metadata_count} metadata record(s) missing;{" "}
                {data.warnings.length} artifact or metadata read error(s).
                Counts include scope members even when their metadata is
                missing.
              </Alert>
            ) : null}
          </>
        ) : null}
      </Stack>
    </Paper>
  );
}
