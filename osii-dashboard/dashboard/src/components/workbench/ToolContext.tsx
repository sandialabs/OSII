import { Stack, Typography } from "@mui/material";
import { documentTools } from "../../domain/workbench";
import { LibraryFlow } from "./LibraryFlow";

export function ToolContext({ id }: { id: (typeof documentTools)[number]["id"] }) {
  const tool = documentTools.find(item => item.id === id);
  if (!tool) return null;
  return (
    <Stack direction="row" gap={1.5} flexWrap="wrap">
      <Typography variant="caption" color="text.secondary" fontWeight={700}>{tool.scope}</Typography>
      <LibraryFlow {...tool.flow} />
    </Stack>
  );
}
