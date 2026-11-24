import { Box, Chip, Stack, Typography } from "@mui/material";
import type { ObjectMeta } from "../../../api/types";
import type { FileDetailModel } from "../../../domain/files";
import { formatFileSize } from "./FileCard";

export function FileDetails({ file, meta }: { file: FileDetailModel; meta: ObjectMeta }) {
  const dateTime = (value?: string | null) => value ? new Date(value).toLocaleString() : null;
  const fields = [
    { label: "Location", value: meta.meta?.source_path || file.sourceRelpath },
    { label: "File type", value: file.mime },
    { label: "Size", value: formatFileSize(meta.file.size_bytes) },
    { label: "Modified", value: dateTime(meta.file.mtime_utc) },
    { label: "Created", value: dateTime(meta.file.birthtime_utc) },
  ].filter(field => field.value);

  return (
    <Stack spacing={1.5}>
      <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: { xs: "1fr", sm: "max-content minmax(0, 1fr)" },
        columnGap: 2, rowGap: 1, "& dd": { m: 0, overflowWrap: "anywhere" } }}>
        {fields.map(({ label, value }) => (
          <Box key={label} sx={{ display: "contents" }}>
            <Typography component="dt" variant="body2" fontWeight={700}>{label}</Typography>
            <Typography component="dd" variant="body2">{value}</Typography>
          </Box>
        ))}
      </Box>
      {(file.sensitivityLabels.length > 0 || file.tags.length > 0) && (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {file.sensitivityLabels.map(label => <Chip key={label} label={label} size="small" color="warning" />)}
          {file.tags.map(tag => <Chip key={tag} label={tag} size="small" variant="outlined" />)}
        </Stack>
      )}
    </Stack>
  );
}
