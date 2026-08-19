// src/features/files/components/markdownSx.ts
import type { SxProps, Theme } from "@mui/material";

/** Shared page styling for rendered wiki Markdown. */
export const markdownSx: SxProps<Theme> = {
          backgroundColor: "background.paper",
          border: (theme) => `1px solid ${theme.palette.divider}`,
          borderRadius: 1.5,
          px: 2.5,
          py: 2,
          "& > :first-of-type": { mt: 0 },
          "& > :last-child": { mb: 0 },
          "& h1": { fontSize: "1.3rem", fontWeight: 700, letterSpacing: "-0.01em", mt: 0, mb: 1.5 },
          "& h2": { fontSize: "1rem", fontWeight: 600, mt: 2.5, mb: 0.75 },
          "& h3": { fontSize: "0.9rem", fontWeight: 600, mt: 2, mb: 0.5 },
          "& p, & li": { fontSize: "0.875rem", lineHeight: 1.7, color: "text.secondary" },
          "& ul, & ol": { pl: 2.5, my: 0.5 },
          "& blockquote": {
            m: 0,
            pl: 1.5,
            borderLeft: (theme) => `3px solid ${theme.palette.primary.main}`,
            color: "text.secondary",
          },
          "& code": {
            backgroundColor: "action.hover",
            px: 0.75,
            py: 0.25,
            borderRadius: 0.75,
            fontSize: "0.8rem",
          },
          "& pre": { overflowX: "auto", backgroundColor: "action.hover", p: 1.5, borderRadius: 1 },
          "& pre code": { backgroundColor: "transparent", p: 0 },
          "& table": { borderCollapse: "collapse" },
          "& td, & th": { border: "1px solid", borderColor: "divider", p: 1 },
          "& a": { color: "secondary.main" },
        };
