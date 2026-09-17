import AutoStoriesOutlinedIcon from "@mui/icons-material/AutoStoriesOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import {
  Alert, Button, Card, CardContent, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteScopeEnrichment } from "../../../api/enrichments";
import { getIntakeReadiness, listProcessingRuns } from "../../../api/queue";
import type { EnrichmentListEntryBundle, EnrichmentListEntryFile, ScopeDescribeRequest } from "../../../api/types";
import { useEnrichmentJob } from "../../../hooks/useEnrichmentJob";
import { useScopeEnrichments } from "../../../hooks/useScopeEnrichments";
import { useScopeEnrichmentPayload } from "../../../hooks/useScopeEnrichmentPayload";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";
import { WikiBundleBrowser } from "./WikiBundleBrowser";

function WikiArtifactCard({ scope, entry }: {
  scope: ScopeDescribeRequest;
  entry: EnrichmentListEntryFile;
}) {
  const queryClient = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const payload = useScopeEnrichmentPayload(scope, entry.name, true);
  const remove = useMutation({
    mutationFn: () => deleteScopeEnrichment({ scope, filename: entry.name }),
    onSuccess: async () => {
      setDeleteOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["enrichments"] });
    },
  });

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
            <Stack spacing={0.25}>
              <Typography fontWeight={700}>{entry.title || entry.name.replace(/\.json$/i, "")}</Typography>
              <Typography variant="caption" color="text.secondary">
                Standard Wiki Markdown · {entry.name}
              </Typography>
            </Stack>
            <Button color="error" size="small" startIcon={<DeleteOutlineOutlinedIcon />} onClick={() => setDeleteOpen(true)} sx={{ alignSelf: "flex-start" }}>
              Delete
            </Button>
          </Stack>
          {payload.isLoading ? <CircularProgress size={22} /> : null}
          {payload.isError ? <Alert severity="warning">This wiki could not be loaded.</Alert> : null}
          {payload.data ? <EnrichmentArtifactView data={payload.data.data} /> : null}
          {remove.isError ? <Alert severity="error">The saved wiki could not be deleted.</Alert> : null}
        </Stack>
      </CardContent>
      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Delete this wiki?</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2">
            This removes only the selected derived artifact and its metadata. Extracted text,
            collection members, and original files are unchanged.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)}>Keep wiki</Button>
          <Button color="error" variant="contained" disabled={remove.isPending} onClick={() => remove.mutate()}>
            {remove.isPending ? "Deleting…" : "Delete wiki"}
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}

export function ScopeWikiPanel({ scope, title }: {
  scope: ScopeDescribeRequest;
  title: string;
}) {
  const enrichmentJob = useEnrichmentJob();
  const enrichments = useScopeEnrichments(scope);
  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness });
  const runs = useQuery({
    queryKey: ["processing-runs"],
    queryFn: listProcessingRuns,
    refetchInterval: (query) => query.state.data?.runs.some(
      (run) => ["queued", "pending", "running"].includes(run.status),
    ) ? 1_200 : 10_000,
  });
  const wikiProcessors = useMemo(() => (readiness.data?.enrichers ?? []).filter(
    (item, index, items) => item.available
      && item.descriptor?.capabilities?.output_kinds?.includes("wiki_markdown")
      && items.findIndex((candidate) => candidate.id === item.id) === index,
  ), [readiness.data?.enrichers]);
  const [selected, setSelected] = useState("");
  useEffect(() => {
    if (!wikiProcessors.some((processor) => processor.id === selected)) {
      setSelected(wikiProcessors[0]?.id ?? "");
    }
  }, [selected, wikiProcessors]);

  const wikiEntry = (enrichments.data?.enrichments ?? []).find(
    (entry): entry is EnrichmentListEntryBundle =>
      entry.kind === "bundle" && entry.name === "wiki--llm_wiki",
  );
  const wikiEntries = (enrichments.data?.enrichments ?? []).filter(
    (entry): entry is EnrichmentListEntryFile => entry.kind === "file" && entry.artifact_type === "wiki_markdown",
  );
  const run = runs.data?.runs.find((item) => item.id === enrichmentJob.data?.run_id);
  const generationActive = enrichmentJob.isPending || ["queued", "pending", "running"].includes(run?.status ?? "");
  const selectedProcessor = wikiProcessors.find((item) => item.id === selected);
  const generate = () => {
    if (!selectedProcessor) return;
    const supportsTitle = Boolean(selectedProcessor.descriptor?.config_schema?.properties?.title);
    enrichmentJob.mutate({
      enricher_name: selectedProcessor.id,
      scope,
      enricher_config: supportsTitle ? { title: `${title} Wiki` } : {},
    });
  };

  return (
    <Stack spacing={2}>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Stack spacing={0.25}>
              <Typography variant="h6" fontWeight={700}>Wiki knowledge products</Typography>
              <Typography variant="body2" color="text.secondary">
                Wiki Markdown is a standard enrichment format. Any registered Processor API
                enricher that declares this output appears here automatically.
              </Typography>
            </Stack>
            {wikiProcessors.length ? (
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "flex-start" }}>
                <TextField select size="small" label="Wiki method" value={selected} onChange={(event) => setSelected(event.target.value)} sx={{ minWidth: 300 }}>
                  {wikiProcessors.map((processor) => (
                    <MenuItem key={processor.id} value={processor.id}>{processor.display_name}</MenuItem>
                  ))}
                </TextField>
                <Button variant="contained" startIcon={<AutoStoriesOutlinedIcon />} disabled={!selectedProcessor || generationActive} onClick={generate}>
                  {generationActive ? "Generating…" : "Generate selected wiki"}
                </Button>
              </Stack>
            ) : (
              <Alert severity="info">
                No Wiki Markdown enricher is connected. Start an optional wiki enricher from
                <strong> osii-toolbox</strong>, then register its Processor API URL in Setup.
              </Alert>
            )}
            <Button
              variant={wikiEntry ? "outlined" : "contained"}
              startIcon={<AutoStoriesOutlinedIcon />}
              disabled={generationActive}
              onClick={() => enrichmentJob.mutate({ enricher_name: "llm_wiki", scope, enricher_config: { title: `${title} Wiki` } })}
            >
              {generationActive ? "Generating…" : wikiEntry ? "Regenerate LLM Wiki" : "Generate LLM Wiki"}
            </Button>
            {selectedProcessor ? <Typography variant="body2" color="text.secondary">{selectedProcessor.description}</Typography> : null}
            {generationActive ? (
              <Alert icon={<CircularProgress size={18} />} severity="info">
                {selectedProcessor?.display_name ?? "The selected processor"} is generating a derived artifact. You can leave this page while it runs.
              </Alert>
            ) : null}
            {run?.status === "error" ? <Alert severity="error">{run.error || run.items?.[0]?.error || "Wiki generation failed."}</Alert> : null}
            {enrichmentJob.isError ? (
              <Alert severity="error">{enrichmentJob.error instanceof Error ? enrichmentJob.error.message : "Could not start wiki generation."}</Alert>
            ) : null}
          </Stack>
        </CardContent>
      </Card>
      {enrichments.isLoading ? <CircularProgress size={22} /> : null}
      {enrichments.isError ? <Alert severity="warning">Saved wikis could not be listed.</Alert> : null}
      {wikiEntry ? <WikiBundleBrowser files={wikiEntry.files} /> : null}
      {wikiEntries.map((entry) => <WikiArtifactCard key={entry.name} scope={scope} entry={entry} />)}
      {!enrichments.isLoading && !wikiEntry && wikiEntries.length === 0 ? (
        <Alert severity="info">No wiki has been generated for this {scope.scope_type} yet.</Alert>
      ) : null}
    </Stack>
  );
}
