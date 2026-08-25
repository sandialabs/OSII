import { useState } from "react";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Stack, Typography } from "@mui/material";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";

import type {
  EnrichmentListEntryFile,
  ScopeDescribeRequest,
} from "../../../api/types";
import { useScopeEnrichmentPayload } from "../../../hooks/useScopeEnrichmentPayload";
import { useScopeEnrichments } from "../../../hooks/useScopeEnrichments";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";
import { ExampleEnrichmentActions } from "./ExampleEnrichmentActions";

function ScopeArtifact({
  scope,
  entry,
}: {
  scope: ScopeDescribeRequest;
  entry: EnrichmentListEntryFile;
}) {
  const [expanded, setExpanded] = useState(false);
  const payload = useScopeEnrichmentPayload(scope, entry.name, expanded);
  return (
    <Accordion expanded={expanded} onChange={(_, next) => setExpanded(next)} variant="outlined" disableGutters>
      <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
        <Stack spacing={0.15}>
          <Typography fontWeight={650}>{entry.name.replace(/\.json$/i, "")}</Typography>
          <Typography variant="caption" color="text.secondary">Open to browse this derived artifact</Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        {payload.isLoading ? <Typography>Loading {entry.name}…</Typography> : null}
        {payload.isError ? <Alert severity="warning">Failed to load {entry.name}.</Alert> : null}
        {payload.data ? <EnrichmentArtifactView data={payload.data.data} /> : null}
      </AccordionDetails>
    </Accordion>
  );
}

export function ScopeEnrichmentsPanel({ scope }: { scope: ScopeDescribeRequest }) {
  const query = useScopeEnrichments(scope);
  if (query.isLoading) return <Typography>Loading enrichments…</Typography>;
  if (query.isError) return <Alert severity="warning">Failed to load enrichments.</Alert>;

  const files = (query.data?.enrichments ?? []).filter(
    (entry): entry is EnrichmentListEntryFile =>
      entry.kind === "file" &&
      entry.name.endsWith(".json") &&
      entry.name !== "wiki--llm_wiki.json" &&
      !entry.name.endsWith(".meta.json"),
  );
  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={700}>Derived artifacts</Typography>
      <ExampleEnrichmentActions scope={scope} />
      {files.length === 0 ? (
        <Alert severity="info">No other derived artifacts are available for this scope.</Alert>
      ) : null}
      {files.map((entry) => (
        <ScopeArtifact key={entry.name} scope={scope} entry={entry} />
      ))}
    </Stack>
  );
}
