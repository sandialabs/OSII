import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { getScopeOverview } from "../../api/scopes";
import type { IntakeReadiness } from "../../api/types";
import {
  libraryWorkflowSteps,
  type WorkflowStepId,
} from "../../domain/workflow";

const ROOT_SCOPE = { scope_type: "root" as const };

export function WorkflowProgress({
  readiness,
  sourceReady,
  checking,
  failed,
  onStep,
}: {
  readiness?: IntakeReadiness;
  sourceReady?: boolean;
  checking?: boolean;
  failed?: boolean;
  onStep: (step: WorkflowStepId) => void;
}) {
  const overview = useQuery({
    queryKey: ["scopes", "overview", ROOT_SCOPE],
    queryFn: () => getScopeOverview(ROOT_SCOPE),
    refetchInterval: 15_000,
    staleTime: 5_000,
  });
  const steps = libraryWorkflowSteps(readiness, overview.data, sourceReady);
  const completed = steps.filter((step) => step.complete).length;
  const unverified = failed || overview.isError;
  const loading = (!readiness && !failed) || overview.isLoading || checking;
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
          <Stack spacing={0.25}>
            <Typography variant="h6" fontWeight={700}>
              Library readiness
            </Typography>
          </Stack>
          <Chip
            variant="outlined"
            color={
              unverified
                ? "warning"
                : completed === steps.length
                  ? "success"
                  : "default"
            }
            label={
              unverified
                ? "Progress unverified"
                : loading
                  ? "Checking progress…"
                  : `${completed} of ${steps.length} complete`
            }
          />
        </Stack>
        <LinearProgress
          aria-label="Library setup and intake progress"
          variant={loading ? "indeterminate" : "determinate"}
          value={(completed / steps.length) * 100}
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
              <Button
                color={step.complete ? "success" : "inherit"}
                onClick={() => onStep(step.id)}
                sx={{
                  textTransform: "none",
                  justifyContent: "flex-start",
                  width: "100%",
                  gap: 1,
                  px: 0.5,
                }}
                aria-label={`${index + 1}. ${step.label}: ${step.complete ? "complete" : "needs attention"}`}
              >
                <Box component="span" sx={{ display: "grid", placeItems: "center", width: 22, height: 22, border: "1px solid", borderColor: step.complete ? "success.main" : "divider", borderRadius: "50%", flexShrink: 0, fontSize: "0.75rem", fontWeight: 700 }}>
                  {index + 1}
                </Box>
                {step.complete ? <CheckCircleOutlineIcon aria-hidden fontSize="small" sx={{ flexShrink: 0, ml: -0.5 }} /> : null}
                <Typography
                  variant="body2"
                  fontWeight={step.complete ? 500 : 700}
                >
                  {step.label}
                </Typography>
              </Button>
            </Box>
          ))}
        </Box>
        {failed || overview.isError ? <Alert severity="warning">{readiness || overview.data ? "Couldn’t refresh readiness. Showing the last check." : "Readiness unavailable. Try refreshing."}</Alert> : null}
      </Stack>
    </Paper>
  );
}
