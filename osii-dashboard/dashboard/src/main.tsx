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