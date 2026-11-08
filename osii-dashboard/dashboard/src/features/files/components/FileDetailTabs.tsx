import { Tab, Tabs } from "@mui/material";
export type FileTab = "text" | "source" | "split" | "extractions" | "syntheses" | "wiki" | "enrichments";
export function FileDetailTabs({ value, onChange }: { value: FileTab; onChange: (tab: FileTab) => void }) {
  return <Tabs value={value} onChange={(_, tab: FileTab) => onChange(tab)} variant="scrollable" scrollButtons="auto" aria-label="Document views">
    <Tab label="Text" value="text" /><Tab label="Source" value="source" /><Tab label="Split View" value="split" /><Tab label="Extractions" value="extractions" /><Tab label="Syntheses" value="syntheses" /><Tab label="Wiki" value="wiki" /><Tab label="Enrichments" value="enrichments" />
  </Tabs>;
}
