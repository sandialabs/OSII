import { Checkbox, List, ListItem, ListItemButton, ListItemText } from "@mui/material";
export type IntakeFile = { path: string; display?: string; size_bytes?: number | null };
function size(value: number | null | undefined): string | undefined {
  if (value == null) return undefined;
  if (value < 1024) return `${value} B`;
  if (value < 1048576) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1048576).toFixed(1)} MB`;
}
export function FileSelectionList({ files, excludedPaths, onToggle }: { files: IntakeFile[]; excludedPaths: string[]; onToggle: (path: string) => void }) {
  return <List dense sx={{ maxHeight: 300, overflow: "auto", bgcolor: "action.hover", borderRadius: 1 }} aria-label="Files included in this run">
    {files.map(file => <ListItem key={file.path} disablePadding><ListItemButton onClick={() => onToggle(file.path)}>
      <Checkbox edge="start" checked={!excludedPaths.includes(file.path)} tabIndex={-1} disableRipple inputProps={{ "aria-label": `Include ${file.display ?? file.path}` }} />
      <ListItemText primary={file.display ?? file.path} secondary={size(file.size_bytes)} primaryTypographyProps={{ variant: "body2", sx: { overflowWrap: "anywhere" } }} />
    </ListItemButton></ListItem>)}
  </List>;
}
