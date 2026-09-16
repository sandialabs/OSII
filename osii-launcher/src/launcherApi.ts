import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import type {
  DeploymentStatus,
  DeploymentPreview,
  PodmanStatus,
  Profile,
  ProfileDraft,
  RegistryStatus,
  SourceCheck,
} from "./types";

export const launcherApi = {
  checkPodman: () => invoke<PodmanStatus>("check_podman"),
  prepareMachine: () => invoke<PodmanStatus>("prepare_podman_machine"),
  registryStatus: (registry: string) =>
    invoke<RegistryStatus>("registry_status", { registry }),
  loginRegistry: (registry: string, username: string, password: string) =>
    invoke<RegistryStatus>("login_registry", { registry, username, password }),
  chooseSource: async () => {
    const choice = await open({ directory: true, multiple: false, title: "Choose a local or already-mounted OSII source folder" });
    return typeof choice === "string" ? choice : null;
  },
  validateSource: (sourceDir: string, probeImage: string) =>
    invoke<SourceCheck>("validate_source", { sourceDir, probeImage }),
  listProfiles: () => invoke<Profile[]>("list_profiles"),
  saveProfile: (draft: ProfileDraft, profileId?: string) =>
    invoke<Profile>("save_profile", { draft, profileId: profileId ?? null }),
  deleteProfile: (profileId: string) => invoke<Profile[]>("delete_profile", { profileId }),
  chooseProfileExport: (name: string) => save({ title: "Export OSII profile", defaultPath: `${name}.osii-profile.toml`, filters: [{ name: "OSII profile", extensions: ["toml"] }] }),
  chooseProfileImport: () => open({ title: "Import OSII profile", multiple: false, filters: [{ name: "OSII profile", extensions: ["toml"] }] }),
  exportProfile: (profileId: string, destination: string) => invoke<void>("export_profile", { profileId, destination }),
  importProfile: (source: string) => invoke<Profile>("import_profile", { source }),
  startProfile: (profileId: string) =>
    invoke<DeploymentStatus>("start_profile", { profileId }),
  stopProfile: (profileId: string) => invoke<DeploymentStatus>("stop_profile", { profileId }),
  deploymentStatus: () => invoke<DeploymentStatus>("deployment_status"),
  deploymentPreview: (profileId: string) =>
    invoke<DeploymentPreview>("deployment_preview", { profileId }),
  logs: (profileId: string) => invoke<string>("profile_logs", { profileId }),
  openDashboard: () => invoke<void>("open_dashboard"),
};
