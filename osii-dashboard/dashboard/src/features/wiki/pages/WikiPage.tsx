// src/features/wiki/pages/WikiPage.tsx
import { Stack, Typography } from "@mui/material";

import { ScopeWikiPanel } from "../../files/components/ScopeWikiPanel";

const ROOT_SCOPE = { scope_type: "root" as const };

export function WikiPage() {
  return (
    <Stack spacing={2}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>
          Wiki
        </Typography>
        <Typography variant="body2" color="text.secondary">
          The library-wide LLM wiki: source pages, entities, and concepts derived from every
          processed file. Per-file wikis live on each file's Wiki tab.
        </Typography>
      </Stack>

      <ScopeWikiPanel scope={ROOT_SCOPE} title="OSII Library" />
    </Stack>
  );
}
