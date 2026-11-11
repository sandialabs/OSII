import { useWorkbenchAvailability } from "../../hooks/useWorkbenchHome";
import { useLocation, useNavigate } from "react-router-dom";
import { workbenchTools } from "../tools";
import { WorkbenchNavigation } from "./WorkbenchLayout";

export function SidebarNav() {
  const navigate = useNavigate();
  const availability = useWorkbenchAvailability();
  const { pathname } = useLocation();
  const current = workbenchTools.find(
    (tool) =>
      pathname === tool.path ||
      (tool.path !== "/" && pathname.startsWith(tool.path + "/")),
  );
  return (
    <WorkbenchNavigation
      availability={availability}
      items={workbenchTools.filter(tool => tool.navigation !== false)}
      selected={current?.id === "tools" ? "overview" : current?.id ?? "home"}
      onNavigate={(id) => {
        const tool = workbenchTools.find((item) => item.id === id);
        if (tool) navigate(tool.path);
      }}
    />
  );
}
