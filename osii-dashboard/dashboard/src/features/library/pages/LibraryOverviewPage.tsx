import { Link } from "react-router-dom";
import { Button, Stack, Typography } from "@mui/material";
import { ScopeOverviewPanel } from "../../../components/discovery/ScopeOverviewPanel";

export function LibraryOverviewPage() {
  return <Stack spacing={2}>
    <Stack direction="row" justifyContent="space-between" alignItems="center"><Typography variant="h4" fontWeight={750}>Analyze Library</Typography><Button component={Link} to="/tools" variant="outlined">All tools</Button></Stack>
    <Typography color="text.secondary">Explore your library’s formats, dates, processing coverage, and topics.</Typography>
    <ScopeOverviewPanel scope={{ scope_type: "root" }} />
  </Stack>;
}
