import { Outlet } from "react-router-dom";
import { SidebarNav } from "./SidebarNav";
import { WorkbenchLayout } from "./WorkbenchLayout";

export function AppLayout() {
  return (
    <WorkbenchLayout navigation={<SidebarNav />}>
      <Outlet />
    </WorkbenchLayout>
  );
}
