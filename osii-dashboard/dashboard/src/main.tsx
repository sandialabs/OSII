// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider } from "@mui/material";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import "katex/dist/katex.min.css";

import { App } from "./app/App";
import { queryClient } from "./app/providers/queryClient";
import { theme } from "./app/theme/theme";
import { BrowsingScopeProvider } from "./app/providers/BrowsingScopeProvider";

import { configureApiClient } from "./api/client";
configureApiClient({
  headers: () => ({ "X-CSRF-Token": decodeURIComponent(document.cookie.split("; ").find(value => value.startsWith("osii_csrf="))?.split("=").slice(1).join("=") ?? "") }),
  unauthorized: () => window.dispatchEvent(new Event("osii-session-expired")),
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <BrowsingScopeProvider>
            <App />
          </BrowsingScopeProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
);