import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type {
  DeploymentStatus,
  DeploymentPreview,
  ModelDiscovery,
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
    const choice = await open({ directory: true, multiple: false, title: "Choose the source folder OSII may read" });
    return typeof choice === "string" ? choice : null;
  },
  validateSource: (sourceDir: string, probeImage: string) =>
    invoke<SourceCheck>("validate_source", { sourceDir, probeImage }),
  discoverModels: (baseUrl: string, apiKey: string) =>
    invoke<ModelDiscovery>("discover_models", {
      baseUrl,
      apiKey,
    }),
  listProfiles: () => invoke<Profile[]>("list_profiles"),
  saveProfile: (draft: ProfileDraft, profileId?: string) =>
    invoke<Profile>("save_profile", { draft, profileId: profileId ?? null }),
  startProfile: (profileId: string, apiKey: string) =>
    invoke<DeploymentStatus>("start_profile", { profileId, apiKey }),
  stopProfile: (profileId: string) => invoke<DeploymentStatus>("stop_profile", { profileId }),
  deploymentStatus: () => invoke<DeploymentStatus>("deployment_status"),
  deploymentPreview: (profileId: string, hasApiKey: boolean) =>
    invoke<DeploymentPreview>("deployment_preview", { profileId, hasApiKey }),
  logs: (profileId: string) => invoke<string>("profile_logs", { profileId }),
  openDashboard: () => invoke<void>("open_dashboard"),
};
