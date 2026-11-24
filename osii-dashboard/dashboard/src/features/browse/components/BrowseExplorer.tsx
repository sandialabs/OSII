import { useState, type ReactNode } from "react";
import {
  Drawer, IconButton, Paper, Stack, Tooltip, Typography, useMediaQuery,
} from "@mui/material";
import CloseOutlined from "@mui/icons-material/CloseOutlined";
import InfoOutlined from "@mui/icons-material/InfoOutlined";
import RefreshOutlined from "@mui/icons-material/RefreshOutlined";
import { BrowseBreadcrumbs } from "./BrowseBreadcrumbs";
import { BrowseDetailsPane } from "./BrowseDetailsPane";
import { FileDisplaySettings } from "../../files/components/FileDisplaySettings";

export function BrowseExplorer({ path, sourceName, onNavigate, onRefresh, children }: {
  path: string;
  sourceName: string;
  onNavigate: (path: string) => void;
  onRefresh: () => void;
  children: ReactNode;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const sideBySide = useMediaQuery("(min-width:1200px)");
  const details = detailsOpen && (
    <Stack spacing={1.5} sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
        <Typography component="h2" variant="subtitle1" fontWeight={700}>Folder Details</Typography>
        <IconButton size="small" aria-label="Close folder details" onClick={() => setDetailsOpen(false)}>
          <CloseOutlined fontSize="small" />
        </IconButton>
      </Stack>
      <BrowseDetailsPane path={path} sourceName={sourceName} />
    </Stack>
  );
  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography component="h1" variant="h5" fontWeight={700}>Browse</Typography>
        <BrowseBreadcrumbs path={path} onNavigate={onNavigate} />
        <Stack direction="row" sx={{ ml: "auto" }}>
          <FileDisplaySettings />
          <Tooltip title="Refresh folder"><IconButton onClick={onRefresh}><RefreshOutlined /></IconButton></Tooltip>
          <Tooltip title="Folder details">
            <IconButton aria-label="Folder details" aria-expanded={detailsOpen} onClick={() => setDetailsOpen(open => !open)}>
              <InfoOutlined />
            </IconButton>
          </Tooltip>
        </Stack>
      </Stack>
      <Stack direction="row" spacing={2} alignItems="flex-start">
        <Stack sx={{ flex: 1, minWidth: 0 }}>{children}</Stack>
        {sideBySide && detailsOpen && (
          <Paper component="aside" aria-label="Folder Details" variant="outlined" sx={{ width: 264, flexShrink: 0 }}>
            {details}
          </Paper>
        )}
      </Stack>
      {!sideBySide && (
        <Drawer anchor="right" open={detailsOpen} onClose={() => setDetailsOpen(false)}
          PaperProps={{ role: "dialog", "aria-label": "Folder Details", sx: { width: "min(320px, 100vw)" } }}>
          {details}
        </Drawer>
      )}
    </Stack>
  );
}
