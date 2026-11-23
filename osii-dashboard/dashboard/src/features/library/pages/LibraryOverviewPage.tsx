import { ToolContext } from "../../../components/workbench/ToolContext";
import { Link } from "react-router-dom";
import { Button, Stack, Typography } from "@mui/material";
import { ScopeOverviewPanel } from "../../../components/discovery/ScopeOverviewPanel";

export function LibraryOverviewPage() {
  return <Stack spacing={2}>
    <Stack direction="row" justifyContent="space-between" alignItems="center"><Typography variant="h4" fontWeight={750}>Analyze Library</Typography><Button component={Link} to="/tools" variant="outlined">Toolbox</Button></Stack>
    <ToolContext id="overview" />
    <ScopeOverviewPanel scope={{ scope_type: "root" }} />
  </Stack>;
}
