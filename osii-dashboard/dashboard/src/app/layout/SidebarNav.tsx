// src/app/layout/SidebarNav.tsx
import {
  Box,
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemText,
  ListSubheader,
  Toolbar,
  Typography,
} from "@mui/material";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import CollectionsBookmarkOutlinedIcon from "@mui/icons-material/CollectionsBookmarkOutlined";
import MoveToInboxOutlinedIcon from "@mui/icons-material/MoveToInboxOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import { useLocation, useNavigate } from "react-router-dom";

type SidebarNavProps = {
  drawerWidth: number;
};

export function SidebarNav({ drawerWidth }: SidebarNavProps) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: drawerWidth,
        flexShrink: 0,
        [`& .MuiDrawer-paper`]: {
          width: drawerWidth,
          boxSizing: "border-box",
          borderRight: (theme) => `1px solid ${theme.palette.divider}`,
        },
      }}
    >
      <Toolbar variant="dense">
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600}>
            Menu
          </Typography>
        </Box>
      </Toolbar>

      <Divider />

      <List
        dense
        subheader={(
          <ListSubheader disableSticky component="div">
            Set up and intake
          </ListSubheader>
        )}
      >
        <ListItemButton
          dense
          selected={location.pathname.startsWith("/admin")}
          onClick={() => navigate("/admin/processors")}
        >
          <SettingsOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Setup" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>
        <ListItemButton
          dense
          selected={location.pathname === "/intake"}
          onClick={() => navigate("/intake")}
        >
          <MoveToInboxOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Intake" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>
      </List>

      <Divider />

      <List
        dense
        subheader={(
          <ListSubheader disableSticky component="div">
            Work with documents
          </ListSubheader>
        )}
      >
        <ListItemButton dense selected={location.pathname === "/"} onClick={() => navigate("/")}>
          <HomeOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Files" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton
          dense
          selected={location.pathname === "/browse"}
          onClick={() => navigate("/browse")}
        >
          <FolderOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Browse" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton
          dense
          selected={location.pathname === "/search"}
          onClick={() => navigate("/search")}
        >
          <SearchOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Search" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton
          dense
          selected={location.pathname === "/chat"}
          onClick={() => navigate("/chat")}
        >
          <ChatOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Chat" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton
          dense
          selected={location.pathname.startsWith("/collections")}
          onClick={() => navigate("/collections")}
        >
          <CollectionsBookmarkOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Collections" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>
      </List>

    </Drawer>
  );
}
