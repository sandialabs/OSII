import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type {
  DeploymentStatus,
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
  listProfiles: () => invoke<Profile[]>("list_profiles"),
  saveProfile: (draft: ProfileDraft, profileId?: string) =>
    invoke<Profile>("save_profile", { draft, profileId: profileId ?? null }),
  storeApiKey: (profileId: string, apiKey: string) =>
    invoke<void>("store_api_key", { profileId, apiKey }),
  forgetApiKey: (profileId: string) => invoke<void>("forget_api_key", { profileId }),
  startProfile: (profileId: string) => invoke<DeploymentStatus>("start_profile", { profileId }),
  stopProfile: (profileId: string) => invoke<DeploymentStatus>("stop_profile", { profileId }),
  deploymentStatus: () => invoke<DeploymentStatus>("deployment_status"),
  logs: (profileId: string) => invoke<string>("profile_logs", { profileId }),
  openDashboard: () => invoke<void>("open_dashboard"),
};
