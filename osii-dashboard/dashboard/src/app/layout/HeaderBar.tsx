// src/app/layout/HeaderBar.tsx
import { AppBar, Box, Toolbar, Typography } from "@mui/material";

export function HeaderBar() {
  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{
        borderBottom: "1px solid rgba(255,255,255,0.10)",
        background: "linear-gradient(90deg, #00415d 0%, #33bdd9 100%)",
        color: "#ffffff",
        zIndex: (theme) => theme.zIndex.drawer - 1,
      }}
    >
      <Toolbar
        sx={{
          minHeight: "75px !important",
          px: 2.5,
        }}
      >
        <Box>
          <Typography
            sx={{
              color: "#ffffff",
              fontWeight: 700,
              fontSize: "1.7rem",
              lineHeight: 1.2,
            }}
          >
            OSII Workbench
          </Typography>
          <Typography
            sx={{
              color: "rgba(255,255,255,0.90)",
              fontSize: "0.9rem",
              lineHeight: 1.25,
              mt: 0.25,
            }}
          >
            Grounded browsing, search, and AI-assisted analysis
          </Typography>
        </Box>
      </Toolbar>
    </AppBar>
  );
}