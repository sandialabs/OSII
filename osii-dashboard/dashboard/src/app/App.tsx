// src/app/App.tsx
import { AppRouter } from "./router";
import { lazy } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, CircularProgress } from "@mui/material";
import { apiJson } from "../api/client";
import { ToolBoundary } from "./ToolBoundary";

const VolumePage = lazy(() => import("../features/volume/VolumePage"));

export function App() {
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: () => apiJson<{ storage_mode: string }>("/api/runtime"),
    staleTime: Infinity,
    retry: false,
  });
  if (runtime.isPending) return <CircularProgress aria-label="Loading OSII" />;
  // A disconnected API must not silently switch to a different store.
  if (runtime.error)
    return (
      <Alert severity="error">
        Cannot identify the OSII store: {runtime.error.message}
      </Alert>
    );
  if (runtime.data.storage_mode === "volume")
    return (
      <ToolBoundary>
        <VolumePage />
      </ToolBoundary>
    );
  return <AppRouter />;
}
