import { MenuItem, TextField } from "@mui/material";

export type SearchMode = "lexical" | "hybrid" | "semantic";
export function SearchModeSelect({ value, onChange }: { value: SearchMode; onChange: (value: SearchMode) => void }) {
  return <TextField select size="small" label="Search mode" value={value} onChange={e => onChange(e.target.value as SearchMode)} sx={{ minWidth: 180 }}
    helperText={value === "lexical" ? "Keyword search · no embedding service needed" : "Uses the configured embedding model"}>
    <MenuItem value="lexical">Keyword (lexical)</MenuItem><MenuItem value="hybrid">Hybrid</MenuItem><MenuItem value="semantic">Semantic</MenuItem>
  </TextField>;
}
