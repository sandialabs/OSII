// src/features/workspace/pages/WorkspacePage.tsx
import { useEffect } from "react";
import { Stack, Typography } from "@mui/material";

import { ScopeFileBrowser } from "../../files/components/ScopeFileBrowser";
import { useBrowsingScope } from "../../../app/providers/BrowsingScopeProvider";
import { ScopeEnrichmentsPanel } from "../../files/components/ScopeEnrichmentsPanel";

export function WorkspacePage() {
  const { setRootScope } = useBrowsingScope();

  useEffect(() => {
    setRootScope();
  }, [setRootScope]);

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>
          Workspace
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Browse all files in the root scope using compact cards with synthesis hover previews.
        </Typography>
      </Stack>

      <ScopeFileBrowser
        scope={{ scope_type: "root" }}
        title="All Files"
        subtitle="Root scope"
        emptyMessage="No files were found in the root scope."
      />
      <ScopeEnrichmentsPanel scope={{ scope_type: "root" }} />
    </Stack>
  );
}
