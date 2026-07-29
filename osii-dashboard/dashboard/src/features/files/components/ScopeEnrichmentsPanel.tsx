import { Alert, Card, CardContent, Stack, Typography } from "@mui/material";

import type {
  EnrichmentListEntryFile,
  ScopeDescribeRequest,
} from "../../../api/types";
import { useScopeEnrichmentPayload } from "../../../hooks/useScopeEnrichmentPayload";
import { useScopeEnrichments } from "../../../hooks/useScopeEnrichments";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";

function ScopeArtifact({
  scope,
  entry,
}: {
  scope: ScopeDescribeRequest;
  entry: EnrichmentListEntryFile;
}) {
  const payload = useScopeEnrichmentPayload(scope, entry.name);
  return (
    <Card>
      <CardContent>
        {payload.isLoading ? <Typography>Loading {entry.name}…</Typography> : null}
        {payload.isError ? <Alert severity="warning">Failed to load {entry.name}.</Alert> : null}
        {payload.data ? <EnrichmentArtifactView data={payload.data.data} /> : null}
      </CardContent>
    </Card>
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
      !entry.name.endsWith(".meta.json"),
  );
  if (files.length === 0) return null;

  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={700}>Derived artifacts</Typography>
      {files.map((entry) => (
        <ScopeArtifact key={entry.name} scope={scope} entry={entry} />
      ))}
    </Stack>
  );
}

