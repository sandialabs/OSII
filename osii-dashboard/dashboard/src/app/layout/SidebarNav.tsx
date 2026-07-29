// src/app/layout/SidebarNav.tsx
import {
  Box,
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemText,
  Toolbar,
  Typography,
} from "@mui/material";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import CollectionsBookmarkOutlinedIcon from "@mui/icons-material/CollectionsBookmarkOutlined";
import QueueOutlinedIcon from "@mui/icons-material/QueueOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import { useNavigate } from "react-router-dom";

type SidebarNavProps = {
  drawerWidth: number;
};

export function SidebarNav({ drawerWidth }: SidebarNavProps) {
  const navigate = useNavigate();

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

      <List dense>
        <ListItemButton dense onClick={() => navigate("/")}>
          <HomeOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Files" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton dense onClick={() => navigate("/browse")}>
          <FolderOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Browse" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton dense onClick={() => navigate("/search")}>
          <SearchOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Search" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton dense onClick={() => navigate("/chat")}>
          <ChatOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Chat" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton dense onClick={() => navigate("/collections")}>
          <CollectionsBookmarkOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Collections" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton dense onClick={() => navigate("/queue")}>
          <QueueOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Processing" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>

        <ListItemButton dense onClick={() => navigate("/admin/processors")}>
          <SettingsOutlinedIcon fontSize="small" style={{ marginRight: 12 }} />
          <ListItemText primary="Admin" primaryTypographyProps={{ variant: "body2" }} />
        </ListItemButton>
      </List>
    </Drawer>
  );
}
