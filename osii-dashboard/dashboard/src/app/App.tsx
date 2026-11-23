import { lazy, Suspense } from "react";

const HostedApp = import.meta.env.MODE === "server"
  ? lazy(async () => ({ default: (await import("../features/server/ServerApp")).ServerApp }))
  : null;

const LocalApp = import.meta.env.MODE !== "server"
  ? lazy(async () => ({ default: (await import("./router")).AppRouter }))
  : null;

export function App() {
  const Shell = HostedApp ?? LocalApp;
  return Shell && <Suspense fallback={<div role="status">Opening OSII…</div>}><Shell /></Suspense>;
}
