// src/features/files/components/FileSynthesesPanel.tsx
import {
  Alert,
  Card,
  CardContent,
  Stack,
  Typography,
} from "@mui/material";

import { useObjectSyntheses } from "../../../hooks/useObjectSyntheses";

type FileSynthesesPanelProps = {
  fileId: string;
};

export function FileSynthesesPanel({ fileId }: FileSynthesesPanelProps) {
  const { data, isLoading, isError, error } = useObjectSyntheses(fileId);

  if (isLoading) {
    return <Typography>Loading syntheses…</Typography>;
  }

  if (isError) {
    return (
      <Alert severity="warning">
        Failed to load syntheses.
        {error instanceof Error ? ` ${error.message}` : ""}
      </Alert>
    );
  }

  if (!data) {
    return <Alert severity="info">No synthesis data available.</Alert>;
  }

  return (
    <Stack spacing={2}>
      <Card>
        <CardContent>
          <Stack spacing={1}>
            <Typography variant="subtitle1" fontWeight={600}>
              Current Synthesis
            </Typography>
            <Typography variant="body2">
              {data.current_text ?? "No current synthesis text is available."}
            </Typography>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack spacing={1}>
            <Typography variant="subtitle1" fontWeight={600}>
              Synthesis Listing
            </Typography>

            {data.syntheses.length > 0 ? (
              data.syntheses.map((item) => (
                <Typography key={`${item.name}-${item.scope}`} variant="body2" color="text.secondary">
                  {item.name} · {item.scope}
                </Typography>
              ))
            ) : (
              <Typography variant="body2" color="text.secondary">
                No synthesis artifacts listed.
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}