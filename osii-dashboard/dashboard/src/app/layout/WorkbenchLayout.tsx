import { useState, type ElementType, type ReactNode } from "react";
import {
  Box, useMediaQuery,
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemText,
  ListSubheader,
  Toolbar,
  Typography,
} from "@mui/material";
import type { ToolAvailability } from "../../domain/workbench";
import { HeaderBar } from "./HeaderBar";

export type NavigationGroup = "home" | "documents" | "tools" | "start" | "setup";
export type NavigationItem = {
  id: string;
  label: string;
  group: NavigationGroup;
  icon: ElementType;
};
const groups: { id: NavigationGroup; label: string }[] = [
  { id: "documents", label: "Library" },
  { id: "tools", label: "Toolbox" },
  { id: "start", label: "Add & process" },
  { id: "setup", label: "Configuration" },
];

/** Product adapters supply routes and capabilities; this component owns no API or auth. */
export function WorkbenchNavigation({
  items,
  selected,
  onNavigate,
  availability,
}: {
  availability?: Record<string, ToolAvailability>;
  items: readonly NavigationItem[];
  selected: string;
  onNavigate: (id: string) => void;
}) {
  return (
    <>
      {items.filter(item => item.group === "home").map(({ id, label, icon: Icon }) => <ListItemButton key={id} selected={selected === id} aria-current={selected === id ? "page" : undefined} onClick={() => onNavigate(id)}><Icon fontSize="small" sx={{ mr: 1.5 }} /><ListItemText primary={label} /></ListItemButton>)}
      <Toolbar variant="dense">
        <Typography variant="caption" color="text.secondary" fontWeight={600}>
          Menu
        </Typography>
      </Toolbar>
      {groups.map((group) => {
        const entries = items.filter((item) => item.group === group.id);
        const landing = entries.find(item => item.id === group.id);
        const orderedEntries = landing ? [landing, ...entries.filter(item => item !== landing)] : entries;
        return entries.length ? (
          <Box key={group.id}>
            <Divider />
            <List
              dense
              subheader={landing ? undefined : (
                <ListSubheader disableSticky component="div">
                  {group.label}
                </ListSubheader>
              )}
            >
              {orderedEntries.map(({ id, label, icon: Icon }) => {
                const state = (group.id === "tools" || id === "browse") ? availability?.[id] : undefined;
                return <ListItemButton
                  key={id}
                  dense
                  disabled={state?.enabled === false}
                  sx={{ "&.Mui-disabled": { opacity: 1, color: "text.secondary" } }}
                  selected={selected === id}
                  aria-current={selected === id ? "page" : undefined}
                  onClick={() => onNavigate(id)}
                >
                  <Icon fontSize="small" sx={{ mr: 1.5 }} />
                  <ListItemText
                    primary={label}
                    secondary={state?.enabled === false ? state.reason : undefined}
                  primaryTypographyProps={{ variant: "body2", fontWeight: id === group.id ? 700 : undefined }}
                  />
                </ListItemButton>;
              })}
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
  const desktop = useMediaQuery("(min-width:900px)");
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem("osii.navigation.collapsed") === "true"; } catch { return false; } });
  const toggleNavigation = () => {
    if (window.matchMedia("(min-width: 900px)").matches) setCollapsed(value => { try { localStorage.setItem("osii.navigation.collapsed", String(!value)); } catch { /* Storage can be disabled. */ } return !value; });
    else setOpen(value => !value);
  };
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
        sx={{ width: { md: collapsed ? 0 : 280 }, flexShrink: { md: 0 } }}
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
            display: { xs: "none", md: collapsed ? "none" : "block" },
            "& .MuiDrawer-paper": paper,
          }}
        >
          {content}
        </Drawer>
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <HeaderBar actions={actions} onOpenNavigation={toggleNavigation} navigationExpanded={desktop ? !collapsed : open} />
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
