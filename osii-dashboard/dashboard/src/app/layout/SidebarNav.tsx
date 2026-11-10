import { useLocation, useNavigate } from "react-router-dom";
import { workbenchTools } from "../tools";
import { WorkbenchNavigation } from "./WorkbenchLayout";

export function SidebarNav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const current = workbenchTools.find(
    (tool) =>
      pathname === tool.path ||
      (tool.path !== "/" && pathname.startsWith(tool.path + "/")),
  );
  return (
    <WorkbenchNavigation
      items={workbenchTools}
      selected={current?.id ?? "files"}
      onNavigate={(id) => {
        const tool = workbenchTools.find((item) => item.id === id);
        if (tool) navigate(tool.path);
      }}
    />
  );
}
