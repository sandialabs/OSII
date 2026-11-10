import { useState, type ElementType, type ReactNode } from "react";
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
import { HeaderBar } from "./HeaderBar";

export type NavigationGroup = "documents" | "tools" | "start" | "setup";
export type NavigationItem = {
  id: string;
  label: string;
  group: NavigationGroup;
  icon: ElementType;
};
const groups: { id: NavigationGroup; label: string }[] = [
  { id: "documents", label: "Library" },
  { id: "tools", label: "Tools" },
  { id: "start", label: "Add & process" },
  { id: "setup", label: "Configuration" },
];

/** Product adapters supply routes and capabilities; this component owns no API or auth. */
export function WorkbenchNavigation({
  items,
  selected,
  onNavigate,
}: {
  items: readonly NavigationItem[];
  selected: string;
  onNavigate: (id: string) => void;
}) {
  return (
    <>
      <Toolbar variant="dense">
        <Typography variant="caption" color="text.secondary" fontWeight={600}>
          Menu
        </Typography>
      </Toolbar>
      {groups.map((group) => {
        const entries = items.filter((item) => item.group === group.id);
        return entries.length ? (
          <Box key={group.id}>
            <Divider />
            <List
              dense
              subheader={
                <ListSubheader disableSticky component="div">
                  {group.label}
                </ListSubheader>
              }
            >
              {entries.map(({ id, label, icon: Icon }) => (
                <ListItemButton
                  key={id}
                  dense
                  selected={selected === id}
                  aria-current={selected === id ? "page" : undefined}
                  onClick={() => onNavigate(id)}
                >
                  <Icon fontSize="small" sx={{ mr: 1.5 }} />
                  <ListItemText
                    primary={label}
                    primaryTypographyProps={{ variant: "body2" }}
                  />
                </ListItemButton>
              ))}
            </List>
          </Box>
        ) : null;
      })}
    </>
  );
}

/** One responsive workbench shell for local and hosted products. */
export function WorkbenchLayout({
  navigation,
  children,
  actions,
  footer,
}: {
  navigation: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const content = (
    <>
      <Box
        onClick={(event) => {
          if ((event.target as Element).closest('button,a,[role="button"]'))
            setOpen(false);
        }}
      >
        {navigation}
      </Box>
      {footer && <Box sx={{ mt: "auto", p: 2 }}>{footer}</Box>}
    </>
  );
  const paper = {
    width: 280,
    boxSizing: "border-box" as const,
    display: "flex",
    borderRight: "1px solid",
    borderColor: "divider",
  };
  return (
    <Box
      sx={{
        display: "flex",
        minHeight: "100vh",
        backgroundColor: "background.default",
      }}
    >
      <Box
        component="nav"
        aria-label="Main navigation"
        sx={{ width: { md: 280 }, flexShrink: { md: 0 } }}
      >
        <Drawer
          variant="temporary"
          open={open}
          onClose={() => setOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: "block", md: "none" },
            "& .MuiDrawer-paper": paper,
          }}
        >
          {content}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: "none", md: "block" },
            "& .MuiDrawer-paper": paper,
          }}
        >
          {content}
        </Drawer>
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <HeaderBar actions={actions} onOpenNavigation={() => setOpen(true)} />
        <Box
          component="main"
          id="workbench-content"
          sx={{ px: { xs: 2, md: 3 }, py: 2.5, maxWidth: "100%" }}
        >
          {children}
        </Box>
      </Box>
    </Box>
  );
}
