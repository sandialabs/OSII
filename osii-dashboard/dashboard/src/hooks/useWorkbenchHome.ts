import { documentTools } from "../domain/workbench";
import { useQuery } from "@tanstack/react-query";
import { getWorkbenchHome } from "../api/workbench";
export function useWorkbenchHome() {
  return useQuery({ queryKey: ["workbench-home"], queryFn: getWorkbenchHome, staleTime: 10_000, refetchInterval: 15_000 });
}

export function useWorkbenchAvailability() {
  const home = useWorkbenchHome();
  return Object.fromEntries(documentTools.map(tool => [tool.id,
    home.isError ? { enabled: false, reason: "Readiness unavailable" }
      : home.isPending ? { enabled: false, reason: "Checking readiness…" }
      : home.data?.tools[tool.id] ?? { enabled: false, reason: "Readiness unavailable" },
  ]));
}
