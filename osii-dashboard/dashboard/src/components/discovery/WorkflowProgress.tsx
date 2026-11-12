import { ReadinessPanel } from "./ReadinessPanel";
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
  return <ReadinessPanel steps={steps} loading={(!readiness && !failed) || overview.isLoading || checking}
    failed={failed || overview.isError} hasPrevious={Boolean(readiness && overview.data)} onStep={onStep} />;
}
