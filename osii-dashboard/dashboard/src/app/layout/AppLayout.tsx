// src/app/layout/AppLayout.tsx
import { Box } from "@mui/material";
import { Outlet } from "react-router-dom";

import { HeaderBar } from "./HeaderBar";
import { SidebarNav } from "./SidebarNav";

const DRAWER_WIDTH = 280;

export function AppLayout() {
  return (
    <Box sx={{ display: "flex", minHeight: "100vh", backgroundColor: "background.default" }}>
      <SidebarNav drawerWidth={DRAWER_WIDTH} />

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <HeaderBar />
        <Box
          component="main"
          sx={{
            px: { xs: 2, md: 3 },
            py: 2.5,
            maxWidth: "100%",
          }}
        >
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}