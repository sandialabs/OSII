import { Stack, Typography } from "@mui/material";
import type { DocumentMetadata } from "../../../api/documentMetadata";
export function SuggestedMetadata({ metadata }: { metadata?: DocumentMetadata | null }) {
  if (!metadata) return null;
  return <Stack spacing={1} aria-label="Suggested document metadata">
    <Typography variant="subtitle2">AI-suggested metadata</Typography>
    <Typography variant="caption" color="text.secondary">{metadata.method === "text_llm" ? "Inferred from extracted text. " : "AI-derived suggestions. "}Verify against the original; unknown fields are left unset.</Typography>
    {(["title", "author", "date"] as const).map(name => <Stack key={name} spacing={0.25}>
      <Typography variant="body2"><strong>{name[0].toUpperCase() + name.slice(1)}:</strong> {metadata[name]?.value || "Unknown"}</Typography>
      {metadata[name]?.qualifier && <Typography variant="body2" color="text.secondary">{metadata[name].qualifier}</Typography>}
      {metadata[name]?.evidence && <Typography variant="caption" component="blockquote" sx={{m:0, pl:1, borderLeft:"2px solid", borderColor:"divider"}}>“{metadata[name].evidence}”</Typography>}
    </Stack>)}
  </Stack>;
}
