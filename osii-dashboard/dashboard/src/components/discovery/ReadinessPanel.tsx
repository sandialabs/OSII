import { useState } from "react";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import CheckCircleOutline from "@mui/icons-material/CheckCircleOutline";
import {
  Alert,
  IconButton, Dialog, DialogTitle, DialogContent, DialogActions,
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";

/** Transport-free readiness display. Product adapters decide what each checkpoint means. */
export function ReadinessPanel<Id extends string>({
  steps,
  loading = false,
  failed = false,
  hasPrevious = false,
  onStep,
  completionLabel = "complete",
}: {
  steps: readonly {
    id: Id;
    label: string;
    complete: boolean;
    detail?: string;
    statusLabel?: string;
    action?: string;
  }[];
  loading?: boolean;
  failed?: boolean;
  hasPrevious?: boolean;
  onStep: (id: Id) => void;
  completionLabel?: string;
}) {
  const completed = steps.filter((step) => step.complete).length;
  const [help, setHelp] = useState(false);
  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 2, sm: 2.5 },
        borderRadius: 2,
        borderColor: "secondary.main",
      }}
    >
      <Stack spacing={1.5}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          justifyContent="space-between"
          spacing={1}
          alignItems={{ sm: "center" }}
        >
          <Stack direction="row" spacing={1} alignItems="center"><Typography variant="h6" fontWeight={700}>
            Your path to AI search &amp; chat
          </Typography>
          <IconButton aria-label="About the path to AI search and chat" onClick={() => setHelp(true)}><HelpOutlineIcon fontSize="small" /></IconButton></Stack>
          <Chip
            variant="outlined"
            color={
              failed
                ? "warning"
                : completed === steps.length
                  ? "success"
                  : "default"
            }
            label={
              failed
                ? "Progress unverified"
                : loading
                  ? "Checking progress…"
                  : `${completed} of ${steps.length} ${completionLabel}`
            }
          />
        </Stack>
        <LinearProgress
          aria-label="Library setup and intake progress"
          variant={loading ? "indeterminate" : "determinate"}
          value={steps.length ? (completed / steps.length) * 100 : 0}
          sx={{ height: 8, borderRadius: 4 }}
        />
        <Box
          component="ol"
          sx={{
            m: 0,
            p: 0,
            listStyle: "none",
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              sm: "repeat(2, 1fr)",
              md: "repeat(3, 1fr)",
            },
            gap: 1,
          }}
        >
          {steps.map((step, index) => (
            <Box component="li" key={step.id}>
              <Tooltip title={step.detail || ""}>
                <Button
                  color={step.complete ? "success" : "inherit"}
                  onClick={() => onStep(step.id)}
                  aria-label={`${index + 1}. ${step.label}: ${step.statusLabel || (step.complete ? "complete" : "needs attention")}`}
                  sx={{
                    textTransform: "none",
                    justifyContent: "flex-start",
                    width: "100%",
                    gap: 1,
                    px: 0.5,
                  }}
                >
                  <Box
                    component="span"
                    sx={{
                      display: "grid",
                      placeItems: "center",
                      width: 22,
                      height: 22,
                      border: "1px solid",
                      borderColor: step.complete ? "success.main" : "divider",
                      borderRadius: "50%",
                      flexShrink: 0,
                      fontSize: ".75rem",
                      fontWeight: 700,
                    }}
                  >
                    {index + 1}
                  </Box>
                  {step.complete && (
                    <CheckCircleOutline
                      aria-hidden
                      fontSize="small"
                      sx={{ flexShrink: 0, ml: -0.5 }}
                    />
                  )}
                  <Typography
                    variant="body2"
                    fontWeight={step.complete ? 500 : 700}
                  >
                    {step.label}
                  </Typography>
                </Button>
              </Tooltip>
            </Box>
          ))}
        </Box>
        {failed && (
          <Alert severity="warning">
            {hasPrevious
              ? "Couldn’t refresh readiness. Showing the last check."
              : "Readiness unavailable. Try refreshing."}
          </Alert>
        )}
        <Dialog open={help} onClose={() => setHelp(false)} fullWidth maxWidth="sm"><DialogTitle>Your path to AI search &amp; chat</DialogTitle><DialogContent><Stack spacing={2}>{steps.map((step, index) => <Box key={step.id}><Typography fontWeight={700}>{index + 1}. {step.label}</Typography><Typography variant="body2">{step.detail}</Typography></Box>)}</Stack></DialogContent><DialogActions><Button onClick={() => setHelp(false)}>Close</Button></DialogActions></Dialog>
      </Stack>
    </Paper>
  );
}
