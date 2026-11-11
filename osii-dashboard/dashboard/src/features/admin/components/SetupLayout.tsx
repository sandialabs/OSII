import type { ReactNode } from "react";
import { Accordion, AccordionDetails, AccordionSummary, Box, Chip, Stack, Typography } from "@mui/material";
import { ExpandMore, TextSnippetOutlined, AutoAwesomeOutlined, HubOutlined, ExtensionOutlined } from "@mui/icons-material";

const capabilities = {
  extractor: ["Extractors", "Turn source files into grounded text and artifacts.", TextSnippetOutlined],
  synthesizer: ["Synthesizers", "Create grounded summaries, titles, and other synthesized text.", AutoAwesomeOutlined],
  embedder: ["Embedders", "Connect an embedding model for semantic search and related documents.", HubOutlined],
  enricher: ["Enrichers", "Create keywords, entities, tables, graphs, and other reusable knowledge products.", ExtensionOutlined],
} as const;
export type CapabilityKind = keyof typeof capabilities;

export function SetupLayout({ children }: { children: ReactNode }) {
  return <Stack spacing={3} sx={{ maxWidth: 1100, mx: "auto" }}>
    <Typography variant="h5" fontWeight={750}>Setup</Typography>{children}
  </Stack>;
}

export function CapabilitySection({ kind, expanded, onChange, summary, available, countLabel = "available", children }: {
  kind: CapabilityKind; expanded: boolean; onChange: (expanded: boolean) => void;
  summary: string; available?: number; countLabel?: string; children: ReactNode;
}) {
  const [title, description, Icon] = capabilities[kind];
  return <Accordion disableGutters elevation={0} expanded={expanded} onChange={(_, value) => onChange(value)}
    slotProps={{ transition: { unmountOnExit: true } }}
    sx={{ border: "1px solid", borderColor: expanded ? "secondary.main" : "divider", borderRadius: "12px !important", overflow: "hidden", "&:before": { display: "none" } }}>
    <AccordionSummary id={`setup-${kind}-heading`} aria-controls={`setup-${kind}-content`} expandIcon={<ExpandMore />}
      sx={{ px: { xs: 1.5, sm: 2 }, minHeight: 80, "&:hover": { bgcolor: "rgba(0,95,114,0.025)" } }}>
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: "100%", minWidth: 0, pr: 1 }}>
        <Box sx={{ display: "grid", placeItems: "center", flexShrink: 0, width: 42, height: 42, borderRadius: 2, bgcolor: "rgba(102,206,227,0.15)", color: "secondary.main" }}><Icon /></Box>
        <Box sx={{ flex: 1, minWidth: 0 }}><Typography fontWeight={750}>{title}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>{summary}</Typography></Box>
        <Chip variant="outlined" label={available === undefined ? "Checking…" : `${available} ${countLabel}`} sx={{ display: { xs: "none", sm: "inline-flex" }, flexShrink: 0 }} />
      </Stack>
    </AccordionSummary>
    <AccordionDetails id={`setup-${kind}-content`} sx={{ px: { xs: 1.5, sm: 2.5 }, pb: 2.5 }}><Stack spacing={1.25}>
      <Typography variant="body2" color="text.secondary">{description}</Typography>{children}
    </Stack></AccordionDetails>
  </Accordion>;
}
