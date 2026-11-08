import type { ReactNode } from "react";
import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
export type ExtractionVersion = { id: string; extractor: { name: string; version: string }; primary: boolean; created_utc: string; text_chars: number; manifest_records: number };
export function ExtractionVersions({ variants, onPromote, promoting = false, children }: { variants: ExtractionVersion[]; onPromote?: (id: string) => void; promoting?: boolean; children?: (variant: ExtractionVersion) => ReactNode }) {
  return <Stack spacing={1.5}>{variants.map(variant => <Paper key={variant.id} variant="outlined" sx={{ p: 1.5 }}>
    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
      <Stack spacing={0.25} minWidth={0}><Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography fontWeight={700}>{variant.extractor.name}</Typography><Chip size="small" label={`v${variant.extractor.version}`} variant="outlined" />{variant.primary && <Chip size="small" label="Primary" color="success" />}
      </Stack><Typography variant="caption" color="text.secondary">{variant.created_utc} · {variant.text_chars.toLocaleString()} characters · {variant.manifest_records} grounded segments</Typography></Stack>
      {!variant.primary && onPromote && <Button variant="outlined" disabled={promoting} onClick={() => onPromote(variant.id)}>Make primary</Button>}
    </Stack>{children?.(variant)}
  </Paper>)}</Stack>;
}
