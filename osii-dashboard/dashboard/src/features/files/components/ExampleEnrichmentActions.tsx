import FormatListNumberedOutlinedIcon from "@mui/icons-material/FormatListNumberedOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import { Alert, Button, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";

import type { ScopeDescribeRequest } from "../../../api/types";
import { useEnrichmentJob } from "../../../hooks/useEnrichmentJob";


export function ExampleEnrichmentActions({ scope }: { scope: ScopeDescribeRequest }) {
  const enrichmentJob = useEnrichmentJob();
  const [requested, setRequested] = useState<"keywords" | "entities" | null>(null);

  const run = (kind: "keywords" | "entities") => {
    setRequested(kind);
    enrichmentJob.mutate({
      enricher_name: kind === "keywords" ? "noun_adjective_ngrams" : "entity_candidates",
      scope,
      enricher_config: kind === "keywords" ? { top_k: 20 } : { top_k: 50 },
    });
  };

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Stack spacing={0.25}>
          <Typography fontWeight={700}>Example enrichments</Typography>
          <Typography variant="body2" color="text.secondary">
            Generate standard artifacts locally. These examples require no model or network connection.
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
        {enrichmentJob.isSuccess ? (
          <Alert severity="success">
            {requested === "keywords" ? "Keyword snapshot" : "Entity list"} generation started. This view updates when it finishes.
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
