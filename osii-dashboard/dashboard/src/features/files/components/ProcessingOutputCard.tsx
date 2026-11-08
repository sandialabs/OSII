import type { ReactNode } from "react";
import { Alert, Card, CardContent, Chip, Stack, Typography } from "@mui/material";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";
export function ProcessingOutputCard({ title, createdAt, model, stale = false, text, markdown, children }: {
  title: string; createdAt?: string; model?: string; stale?: boolean; text?: string; markdown?: string; children?: ReactNode;
}) {
  return <Card variant="outlined"><CardContent><Stack spacing={1.5}>
    <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center"><Typography variant="subtitle1" fontWeight={600}>{title}</Typography>{model && <Chip size="small" label={`Model: ${model}`} />}{createdAt && <Typography variant="caption" color="text.secondary">{new Date(createdAt).toLocaleString()}</Typography>}</Stack>
    {stale && <Alert severity="warning">This output used an older primary extraction. It is preserved for comparison; stage processing again for the current text.</Alert>}
    {markdown !== undefined && <EnrichmentArtifactView showTitle={false} data={{ artifact_type: "wiki_markdown", title, markdown, citations: [] }} />}
    {text !== undefined && <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{text}</Typography>}
    {children}
  </Stack></CardContent></Card>;
}
