import { Component, Suspense, type ReactNode } from "react";
import { Alert, Button, LinearProgress, Stack } from "@mui/material";

class ToolErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? (
      <Alert severity="error" action={<Button color="inherit" onClick={() => window.location.reload()}>Reload</Button>}>
        This tool could not be opened. Reload to retry, or choose another tool from the menu.
      </Alert>
    ) : this.props.children;
  }
}

export function ToolBoundary({ children }: { children: ReactNode }) {
  return <ToolErrorBoundary><Suspense fallback={<Stack role="status" aria-label="Loading tool"><LinearProgress /></Stack>}>
    {children}
  </Suspense></ToolErrorBoundary>;
}
