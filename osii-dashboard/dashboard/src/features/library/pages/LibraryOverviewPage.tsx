import { Stack, Typography } from "@mui/material";
import { ScopeOverviewPanel } from "../../../components/discovery/ScopeOverviewPanel";

export function LibraryOverviewPage() {
  return <Stack spacing={2}>
    <Typography component="h1" variant="h4" fontWeight={750}>Analyze Library</Typography>
    <ScopeOverviewPanel scope={{ scope_type: "root" }} />
  </Stack>;
}
