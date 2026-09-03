import FormatListNumberedOutlinedIcon from "@mui/icons-material/FormatListNumberedOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import { Alert, Box, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getIntakeReadiness } from "../../../api/queue";
import type { ScopeDescribeRequest } from "../../../api/types";
import { useEnrichmentJob } from "../../../hooks/useEnrichmentJob";


export function ExampleEnrichmentActions({ scope }: { scope: ScopeDescribeRequest }) {
  const enrichmentJob = useEnrichmentJob();
  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness });
  const [requested, setRequested] = useState<string | null>(null);
  const [selectedEnricher, setSelectedEnricher] = useState("");
  const additionalEnrichers = (readiness.data?.enrichers ?? []).filter(
    (item, index, items) => item.available
      && !["noun_adjective_ngrams", "entity_candidates", "llm_wiki"].includes(item.id)
      && items.findIndex((candidate) => candidate.id === item.id) === index,
  );

  const run = (kind: "keywords" | "entities") => {
    setRequested(kind === "keywords" ? "Keyword snapshot" : "Entity list");
    enrichmentJob.mutate({
      enricher_name: kind === "keywords" ? "noun_adjective_ngrams" : "entity_candidates",
      scope,
      enricher_config: kind === "keywords" ? { top_k: 20 } : { top_k: 50 },
    });
  };

  const runSelected = () => {
    const method = additionalEnrichers.find((item) => item.id === selectedEnricher);
    if (!method) return;
    setRequested(method.display_name);
    enrichmentJob.mutate({ enricher_name: method.id, scope });
  };

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Stack spacing={0.25}>
          <Typography fontWeight={700}>{scope.scope_type === "collection" ? "Generate a collection enrichment" : "Example enrichments"}</Typography>
          <Typography variant="body2" color="text.secondary">
            {scope.scope_type === "collection"
              ? "Keywords and entities are combined across the collection's extracted documents, not generated separately for each file. These two methods need no model; other methods may use connected services."
              : "Generate standard artifacts locally. These examples require no model or network connection."}
          </Typography>
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <Button
            variant="outlined"
            startIcon={<FormatListNumberedOutlinedIcon />}
            disabled={enrichmentJob.isPending}
            onClick={() => run("keywords")}
          >
            Generate Keyword Snapshot
          </Button>
          <Button
            variant="outlined"
            startIcon={<HubOutlinedIcon />}
            disabled={enrichmentJob.isPending}
            onClick={() => run("entities")}
          >
            Generate Entity List
          </Button>
        </Stack>
        {additionalEnrichers.length ? (
          <Box component="details">
            <Typography component="summary" variant="body2" sx={{ cursor: "pointer" }}>
              More available enrichment methods
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1 }}>
              <TextField
                select
                size="small"
                label="Enrichment method"
                value={selectedEnricher}
                onChange={(event) => setSelectedEnricher(event.target.value)}
                sx={{ minWidth: 280 }}
              >
                {additionalEnrichers.map((item) => (
                  <MenuItem key={item.id} value={item.id}>{item.display_name}</MenuItem>
                ))}
              </TextField>
              <Button
                variant="outlined"
                disabled={!selectedEnricher || enrichmentJob.isPending}
                onClick={runSelected}
              >
                Generate selected artifact
              </Button>
            </Stack>
          </Box>
        ) : null}
        {enrichmentJob.isSuccess ? (
          <Alert severity="success">
            {requested ?? "Enrichment"} generation started. This view updates when it finishes.
          </Alert>
        ) : null}
        {enrichmentJob.isError ? (
          <Alert severity="error">
            {enrichmentJob.error instanceof Error ? enrichmentJob.error.message : "Could not start enrichment."}
          </Alert>
        ) : null}
      </Stack>
    </Paper>
  );
}
