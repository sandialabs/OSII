import type { ReactNode } from "react";
import { Box, List, ListItemButton, ListSubheader, Paper, Stack, Typography } from "@mui/material";
import { DocumentSplitPane } from "./SplitFileView";

export type DocumentViewMode = "source" | "split" | "text";

export type DocumentProductGroup = {
  label: string;
  entries: { id: string; label: string; detail?: string }[];
};

export function DocumentWorkspace({ header, groups, selected, onSelect, catalogStatus, sourcePane, children }: {
  header: ReactNode;
  groups: DocumentProductGroup[];
  selected: string;
  onSelect: (id: string) => void;
  catalogStatus?: ReactNode;
  sourcePane?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Stack spacing={2}>
      {header}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "240px minmax(0, 1fr)" }, gap: 2, alignItems: "start" }}>
        <Paper component="nav" aria-label="File products" variant="outlined" sx={{ maxHeight: { xs: 250, md: "calc(100vh - 120px)" }, overflow: "auto", position: { md: "sticky" }, top: 80 }}>
          <Typography component="h2" variant="subtitle1" fontWeight={750} sx={{ px: 1.5, py: 1 }}>File products</Typography>
          {catalogStatus}
          {groups.map(group => (
            <List key={group.label} dense disablePadding aria-label={group.label}
              sx={{ borderTop: 1, borderColor: "divider", pb: 0.5 }}
              subheader={<ListSubheader disableSticky sx={{ px: 1.5, py: 0.5, lineHeight: 2,
                bgcolor: "action.hover", color: "text.primary", fontWeight: 700 }}>{group.label}</ListSubheader>}>
              {group.entries.map(entry => (
                <ListItemButton key={entry.id} selected={selected === entry.id} aria-current={selected === entry.id ? "true" : undefined}
                  onClick={() => onSelect(entry.id)} sx={{ mx: 0.5, px: 1, mt: 0.5, borderRadius: 1 }}>
                  <Stack minWidth={0}>
                    <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{entry.label}</Typography>
                    {entry.detail && <Typography variant="caption" color="text.secondary">{entry.detail}</Typography>}
                  </Stack>
                </ListItemButton>
              ))}
            </List>
          ))}
        </Paper>
        <Box component="section" aria-labelledby="file-product-title" sx={{ minWidth: 0 }}>
          {sourcePane ? <DocumentSplitPane source={sourcePane}>{children}</DocumentSplitPane> : children}
        </Box>
      </Box>
    </Stack>
  );
}
