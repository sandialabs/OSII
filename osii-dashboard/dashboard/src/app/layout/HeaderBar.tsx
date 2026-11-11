import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import {
  AppBar,
  Box,
  IconButton,
  Stack,
  Toolbar,
  Typography,
} from "@mui/material";
import MenuOutlined from "@mui/icons-material/MenuOutlined";

export function HeaderBar({
  actions,
  onOpenNavigation,
}: {
  actions?: ReactNode;
  onOpenNavigation?: () => void;
}) {
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
          gap: 1.5,
          flexWrap: { xs: "wrap", sm: "nowrap" },
          py: { xs: 1, sm: 0 },
        }}
      >
        {onOpenNavigation && (
          <IconButton
            color="inherit"
            aria-label="Open navigation"
            onClick={onOpenNavigation}
            sx={{ display: { md: "none" } }}
          >
            <MenuOutlined />
          </IconButton>
        )}
        <Box component="img" src="/corp-logo.png" alt="OSII magnifying glass" sx={{ width: 44, height: 44, flexShrink: 0 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography component={Link} to="/"
            sx={{ textDecoration: "none",
              color: "#ffffff",
              fontWeight: 700,
              fontSize: { xs: "1.35rem", sm: "1.7rem" },
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
        {actions && (
          <Stack direction="row" spacing={0.5} sx={{ width: { xs: "100%", sm: "auto" }, justifyContent: "flex-end" }}>
            {actions}
          </Stack>
        )}
      </Toolbar>
    </AppBar>
  );
}
