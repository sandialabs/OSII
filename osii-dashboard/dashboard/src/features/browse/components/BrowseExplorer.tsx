import { useState, type ComponentProps } from "react";
import { Accordion, AccordionDetails, AccordionSummary, Alert, CircularProgress, Stack, Typography } from "@mui/material";
import { ExpandMoreOutlined } from "@mui/icons-material";
import { BrowseBreadcrumbs } from "./BrowseBreadcrumbs";
import { BrowseGrid } from "./BrowseGrid";
import { BrowseDetailsPane } from "./BrowseDetailsPane";
import type { FolderScopeDescriptor } from "../../../api/types";

/** Explorer presentation; local/server adapters own catalog transport and routing. */
export function BrowseExplorer({ breadcrumbs, onNavigate, currentFolder, loading, error, ...grid }: ComponentProps<typeof BrowseGrid> & {
  breadcrumbs: FolderScopeDescriptor[]; onNavigate: (id: string) => void;
  currentFolder: FolderScopeDescriptor; loading?: boolean; error?: string;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  return <Stack spacing={1.75}>
    <Stack spacing={0.35}><Typography variant="h5" fontWeight={700}>Browse</Typography>
      <Typography variant="body2" color="text.secondary">Open a folder to see its contents. Only files in the current folder appear here.</Typography></Stack>
    <BrowseBreadcrumbs items={breadcrumbs} onNavigate={onNavigate} />
    {loading ? <Stack direction="row" spacing={2} alignItems="center"><CircularProgress size={24} /><Typography>Loading folder contents…</Typography></Stack>
      : error ? <Alert severity="error">{error}</Alert> : <BrowseGrid {...grid} />}
    <Accordion expanded={detailsOpen} onChange={(_, open) => setDetailsOpen(open)} variant="outlined" disableGutters slotProps={{ transition: { unmountOnExit: true } }}>
      <AccordionSummary expandIcon={<ExpandMoreOutlined />}><Typography variant="body2">Folder details &amp; synthesis</Typography></AccordionSummary>
      <AccordionDetails><BrowseDetailsPane selection={{ kind: "folder", folder: currentFolder }} /></AccordionDetails>
    </Accordion>
  </Stack>;
}
