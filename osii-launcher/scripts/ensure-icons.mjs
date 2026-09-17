import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const project = resolve(fileURLToPath(new URL("..", import.meta.url)));
const icon = resolve(project, "src-tauri/icons/icon.ico");

if (!existsSync(icon)) {
  const source = resolve(project, "src-tauri/icons/icon-source.svg");
  const binary = resolve(
    project,
    process.platform === "win32" ? "node_modules/.bin/tauri.cmd" : "node_modules/.bin/tauri",
  );
  const result = spawnSync(binary, ["icon", source], { cwd: project, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0 || !existsSync(icon)) {
    throw new Error("Could not generate the required Windows icon from icon-source.svg.");
  }
}
