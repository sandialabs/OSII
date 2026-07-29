// src/app/theme/theme.ts
import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#66cee3",
    },
    secondary: {
      main: "#005f72",
    },
    background: {
      default: "#f8fafc",
      paper: "#ffffff",
    },
    info: {
      main: "#00add0",
    },
  },
  shape: {
    borderRadius: 8,
  },
  typography: {
    fontFamily: [
      "Inter",
      "Segoe UI",
      "Roboto",
      "Helvetica Neue",
      "Arial",
      "sans-serif",
    ].join(","),
    h5: {
      fontSize: "1.45rem",
      letterSpacing: "-0.01em",
    },
    h6: {
      fontSize: "1.05rem",
      letterSpacing: "-0.01em",
    },
    subtitle1: {
      fontSize: "0.98rem",
    },
    subtitle2: {
      fontSize: "0.9rem",
    },
    body1: {
      fontSize: "0.95rem",
    },
    body2: {
      fontSize: "0.875rem",
    },
    caption: {
      fontSize: "0.76rem",
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid rgba(15, 23, 42, 0.08)",
          boxShadow: "0 1px 2px rgba(15, 23, 42, 0.05)",
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backdropFilter: "blur(6px)",
        },
      },
    },
    MuiButton: {
      defaultProps: {
        size: "small",
      },
    },
    MuiChip: {
      defaultProps: {
        size: "small",
      },
      styleOverrides: {
        root: {
          borderRadius: 999,
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: {
          backgroundColor: "#00add0",
        },
      },
    },
  },
});