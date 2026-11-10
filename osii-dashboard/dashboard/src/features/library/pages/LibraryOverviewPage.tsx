import { Stack, Typography } from "@mui/material";
import { ScopeOverviewPanel } from "../../../components/discovery/ScopeOverviewPanel";

export function LibraryOverviewPage() {
  return <Stack spacing={2}>
    <Typography color="text.secondary">Explore your library’s formats, dates, processing coverage, and topics.</Typography>
    <ScopeOverviewPanel scope={{ scope_type: "root" }} />
  </Stack>;
}
