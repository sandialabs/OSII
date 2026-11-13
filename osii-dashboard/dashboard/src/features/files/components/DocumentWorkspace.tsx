import { useState, useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Box, Button, IconButton, List, ListItemButton, ListItemText, Stack, ToggleButton, ToggleButtonGroup, Typography, useMediaQuery } from "@mui/material";
import { Close, Inventory2Outlined } from "@mui/icons-material";

export type DocumentViewMode = "source" | "split" | "text";
export type SavedDocumentPanel = { id: string; label: string; description?: string };

/** Reading layout only. Product adapters supply saved data and authenticated actions. */
export function DocumentWorkspace({ header, mode, onMode, panels, renderPanel, children, loading = false, initialPanel }: {
  header: ReactNode; mode: DocumentViewMode; onMode: (mode: DocumentViewMode) => void;
  panels: SavedDocumentPanel[]; renderPanel: (id: string) => ReactNode; children: ReactNode; loading?: boolean; initialPanel?: string;
}) {
  const desktop = useMediaQuery("(min-width:1200px)");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => { if(initialPanel) { setOpen(true); setSelected(initialPanel); } },[initialPanel]);
  useEffect(() => { if (!open) return; const close = (event: KeyboardEvent) => { if(event.key === "Escape") setOpen(false); }; window.addEventListener("keydown", close); return () => window.removeEventListener("keydown", close); }, [open]);
  return <Stack spacing={1.5} sx={{ minWidth: 0 }}>
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Box sx={{ flex: 1, minWidth: 0 }}>{header}</Box>
      <ToggleButtonGroup size="small" exclusive value={mode} onChange={(_, value) => { if(value) onMode(value); }} aria-label="Reading view">
        <ToggleButton value="source">Source</ToggleButton><ToggleButton value="split">Split view</ToggleButton><ToggleButton value="text">Text</ToggleButton>
      </ToggleButtonGroup>
      <Button size="small" startIcon={<Inventory2Outlined/>} aria-label="Toggle saved data" aria-expanded={open} onClick={() => setOpen(value => !value)}>Saved data</Button>
    </Stack>
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, position: "relative", minWidth: 0 }}>
      <Box sx={{ flex: 1, minWidth: 0 }}>{children}</Box>
      {open ? <Box component="aside" aria-label="Saved document data" sx={{ width: desktop ? 360 : "min(90vw, 400px)", flexShrink: 0, position: desktop ? "sticky" : "fixed", top: desktop ? 90 : 80, right: desktop ? undefined : 8, zIndex: desktop ? 1 : 1200, maxHeight: "calc(100vh - 110px)", overflowY: "auto", bgcolor: "background.paper", border: 1, borderColor: "divider", borderRadius: 1, p: 1.5, boxShadow: desktop ? 0 : 8 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between"><Typography fontWeight={700}>Saved data</Typography><IconButton aria-label="Close saved data" onClick={() => setOpen(false)}><Close fontSize="small" /></IconButton></Stack>
        <Typography variant="caption" color="text.secondary">Read saved summaries, wiki pages and other results. Run tools from the Toolbox.</Typography>
        <List dense aria-label="Saved document products">
          {panels.map(panel => <ListItemButton key={panel.id} selected={selected === panel.id} onClick={() => setSelected(panel.id)}><ListItemText primary={panel.label} secondary={panel.description} primaryTypographyProps={{ variant: "body2" }} secondaryTypographyProps={{ variant: "caption" }} /></ListItemButton>)}
        </List>
        {!panels.length && <Typography variant="body2" color="text.secondary">{loading ? "Loading saved data…" : "No saved products yet."}</Typography>}
        <Button component={Link} to="/tools" size="small">Open Toolbox</Button>
        {selected && panels.some(panel => panel.id === selected) && <Box sx={{ mt: 1.5, minWidth: 0 }}>{renderPanel(selected)}</Box>}
      </Box> : null}
    </Box>
  </Stack>;
}
