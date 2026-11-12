import { Alert, Box, Button, Card, CardActionArea, CardContent, LinearProgress, Stack, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { documentTools } from "../../../domain/workbench";
import { useWorkbenchHome } from "../../../hooks/useWorkbenchHome";
import { dismissHomeSetup } from "../../../api/workbench";

export function WorkbenchHome({ setupPath, toolsOnly = false }: { setupPath: string; toolsOnly?: boolean }) {
  const home = useWorkbenchHome();
  const client = useQueryClient();
  const dismiss = useMutation({ mutationFn: dismissHomeSetup, onSuccess: () => client.invalidateQueries({ queryKey: ["workbench-home"] }) });
  return <Stack spacing={3} sx={{ maxWidth: 1200, mx: "auto" }}>
    <Stack spacing={0.5}><Typography id="workbench-title" variant="h4" fontWeight={750}>{toolsOnly ? "Toolbox" : "Welcome to OSII"}</Typography><Typography color="text.secondary">Choose what you’d like to do with your documents.</Typography></Stack>
    {home.isPending ? <Stack spacing={1}><LinearProgress aria-label="Checking tool readiness" /><Typography role="status">Checking what’s ready…</Typography></Stack> : null}
    {home.isError ? <Alert severity="warning" action={<Button onClick={() => void home.refetch()}>Retry</Button>}>Could not check tool readiness. Your library and settings are unchanged.</Alert> : null}
    {!toolsOnly && !home.isError && home.data?.setup.visible ? <Card variant="outlined" component="section" aria-labelledby="home-setup-title"><CardContent><Stack spacing={1.5}>
      <Typography id="home-setup-title" variant="h6" fontWeight={700}>Setup</Typography>
      <Typography>Connect your processors and models, then add documents. You can return to Setup from the sidebar at any time.</Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <Button component={Link} to={setupPath} variant="outlined">Open Setup</Button>
        <Button component={Link} to="/intake" variant="contained">Add documents</Button>
        <Button disabled={dismiss.isPending} onClick={() => dismiss.mutate()}>Done with setup</Button>
      </Stack>
      {dismiss.isError ? <Alert severity="error">Could not save your choice. Please try again.</Alert> : null}
    </Stack></CardContent></Card> : null}
    <Stack component="section" spacing={2} aria-labelledby={toolsOnly ? "workbench-title" : "document-tools-title"}>
      {!toolsOnly && <Typography id="document-tools-title" variant="h5" fontWeight={700}>Toolbox</Typography>}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(3, minmax(0, 1fr))" }, gap: 2 }}>
        {documentTools.map(tool => {
          const state = home.isError || home.isPending ? undefined : home.data?.tools[tool.id];
          const enabled = state?.enabled === true;
          const reason = home.isError ? "Readiness unavailable — retry above" : state?.reason ?? "Checking readiness…";
          return <Card key={tool.id} variant="outlined" sx={{ bgcolor: enabled ? "background.paper" : "action.disabledBackground", color: enabled ? "text.primary" : "text.secondary", height: "100%" }}>
            <CardActionArea component={Link} to={tool.path} disabled={!enabled} aria-disabled={!enabled} aria-describedby={`tool-${tool.id}-reason`} sx={{ height: "100%", alignItems: "stretch" }}>
              <CardContent sx={{ height: "100%", boxSizing: "border-box" }}><Stack spacing={1.25}>
                <Box aria-hidden sx={{ fontSize: "2.5rem", filter: enabled ? undefined : "grayscale(1)" }}>{tool.illustration}</Box>
                <Typography variant="h6" fontWeight={700}>{tool.label}</Typography>
                <Typography variant="body2">{tool.description}</Typography>
                <Typography id={`tool-${tool.id}-reason`} variant="caption" sx={{ display: "block" }}>{reason}</Typography>
              </Stack></CardContent>
            </CardActionArea>
          </Card>;
        })}
      </Box>
    </Stack>
  </Stack>;
}
