import { Box, Divider, Drawer, List, ListItemButton, ListItemText, ListSubheader, Toolbar, Typography } from "@mui/material";
import { useLocation, useNavigate } from "react-router-dom";
import { workbenchTools } from "../tools";

type SidebarNavProps = { drawerWidth: number };

export function SidebarNav({ drawerWidth }: SidebarNavProps) {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <Drawer variant="permanent" sx={{ width: drawerWidth, flexShrink: 0,
      [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: "border-box", borderRight: theme => `1px solid ${theme.palette.divider}` } }}>
      <Toolbar variant="dense"><Box><Typography variant="caption" color="text.secondary" fontWeight={600}>Menu</Typography></Box></Toolbar>
      {(["start", "documents"] as const).map(group => (
        <Box key={group}>
          <Divider />
          <List dense subheader={<ListSubheader disableSticky component="div">{group === "start" ? "Start here" : "Work with documents"}</ListSubheader>}>
            {workbenchTools.filter(tool => tool.group === group).map(({ id, path, label, description, icon: Icon }) => (
              <ListItemButton key={id} dense selected={location.pathname === path || (path !== "/" && location.pathname.startsWith(path + "/"))} onClick={() => navigate(path)}>
                <Icon fontSize="small" sx={{ mr: 1.5 }} />
                <ListItemText primary={label} secondary={description} primaryTypographyProps={{ variant: "body2" }} secondaryTypographyProps={{ variant: "caption" }} />
              </ListItemButton>
            ))}
          </List>
        </Box>
      ))}
    </Drawer>
  );
}
