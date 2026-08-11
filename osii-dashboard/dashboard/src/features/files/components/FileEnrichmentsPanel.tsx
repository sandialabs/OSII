// src/features/files/components/FileEnrichmentsPanel.tsx
import {
  Alert,
  Button,
  Card,
  CardContent,
  Stack,
  Typography,
} from "@mui/material";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";

import { getArtifactUrl } from "../../../api/artifacts";
import type { EnrichmentListEntryFile } from "../../../api/types";
import { useObjectEnrichmentPayload } from "../../../hooks/useObjectEnrichmentPayload";
import { useScopeEnrichments } from "../../../hooks/useScopeEnrichments";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";
import { ExampleEnrichmentActions } from "./ExampleEnrichmentActions";

type FileEnrichmentsPanelProps = {
  fileId: string;
};

function EnrichmentFileCard({
  fileId,
  entry,
}: {
  fileId: string;
  entry: EnrichmentListEntryFile;
}) {
  const canPreview = entry.name.endsWith(".json") && !entry.name.endsWith(".meta.json");
  const payload = useObjectEnrichmentPayload(fileId, entry.name, canPreview);

  return (
    <Card>
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
            <Typography variant="subtitle1" fontWeight={600}>{entry.name}</Typography>
            <Button
              size="small"
              variant="outlined"
              startIcon={<OpenInNewOutlinedIcon />}
              component="a"
              href={getArtifactUrl(entry.relpath)}
              target="_blank"
              rel="noreferrer"
            >
              Raw artifact
            </Button>
          </Stack>
          {canPreview && payload.isLoading ? <Typography>Loading artifact…</Typography> : null}
          {canPreview && payload.isError ? (
            <Alert severity="warning">The artifact could not be rendered.</Alert>
          ) : null}
          {canPreview && payload.data ? <EnrichmentArtifactView data={payload.data.data} /> : null}
        </Stack>
      </CardContent>
    </Card>
  );
}

export function FileEnrichmentsPanel({ fileId }: FileEnrichmentsPanelProps) {
  const { data, isLoading, isError, error } = useScopeEnrichments({
    scope_type: "object",
    file_id: fileId,
  });

  if (isLoading) {
    return <Typography>Loading enrichments…</Typography>;
  }

  if (isError) {
    return (
      <Alert severity="warning">
        Failed to load enrichments.
        {error instanceof Error ? ` ${error.message}` : ""}
      </Alert>
    );
  }

  const enrichments = (data?.enrichments ?? []).filter(
    (entry) => entry.kind !== "file" || (
      !entry.name.endsWith(".meta.json") && entry.name !== "wiki--llm_wiki.json"
    ),
  );

  return (
    <Stack spacing={2}>
      <ExampleEnrichmentActions scope={{ scope_type: "object", file_id: fileId }} />
      {enrichments.length === 0 ? (
        <Alert severity="info">No other enrichments are available for this file.</Alert>
      ) : null}
      {enrichments.map((entry) => (
        entry.kind === "file" ? (
          <EnrichmentFileCard
            key={`${entry.kind}-${entry.name}`}
            fileId={fileId}
            entry={entry}
          />
        ) : (
        <Card key={`${entry.kind}-${entry.name}`}>
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="subtitle1" fontWeight={600}>
                {entry.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {entry.kind}
              </Typography>

              <Stack spacing={1}>
                <Typography variant="body2" color="text.secondary">
                  Bundle files:
                </Typography>
                {entry.files.map((file) => (
                  <Button
                    key={file.relpath}
                    variant="outlined"
                    startIcon={<OpenInNewOutlinedIcon />}
                    component="a"
                    href={getArtifactUrl(file.relpath)}
                    target="_blank"
                    rel="noreferrer"
                    sx={{ alignSelf: "flex-start" }}
                  >
                    {file.name}
                  </Button>
                ))}
              </Stack>
            </Stack>
          </CardContent>
        </Card>
        )
      ))}
    </Stack>
  );
}
