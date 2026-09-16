import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import type {
  DeploymentStatus,
  DeploymentPreview,
  ActivityRecord,
  CatalogResponse,
  CustomContainerDraft,
  ImageInventory,
  ManagedContainer,
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
  fetchCatalog: (url: string, registry: string) => invoke<CatalogResponse>("fetch_catalog", { url, registry }),
  imageInventory: (references: string[]) => invoke<ImageInventory>("image_inventory", { references }),
  pullImages: (references: string[], registry: string) => invoke<ImageInventory>("pull_images", { references, registry }),
  listActivity: () => invoke<ActivityRecord[]>("list_activity"),
  chooseSource: async () => {
    const choice = await open({ directory: true, multiple: false, title: "Choose a local or already-mounted OSII source folder" });
    return typeof choice === "string" ? choice : null;
  },
  validateSource: (sourceDir: string, probeImage: string) =>
    invoke<SourceCheck>("validate_source", { sourceDir, probeImage }),
  listProfiles: () => invoke<Profile[]>("list_profiles"),
  saveProfile: (draft: ProfileDraft, profileId?: string) =>
    invoke<Profile>("save_profile", { draft, profileId: profileId ?? null }),
  prepareDemoProfile: (draft: ProfileDraft) => invoke<Profile>("prepare_demo_profile", { draft }),
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
  listCustomContainers: () => invoke<CustomContainerDraft[]>("list_custom_containers"),
  saveCustomContainer: (draft: CustomContainerDraft) => invoke<CustomContainerDraft>("save_custom_container", { draft }),
  managedContainers: () => invoke<ManagedContainer[]>("managed_containers"),
  runCustomContainer: (customId: string) => invoke<ManagedContainer>("run_custom_container", { customId }),
  manageContainer: (name: string, action: string, confirmed = false) => invoke<string>("manage_container", { name, action, confirmed }),
  openDashboard: () => invoke<void>("open_dashboard"),
};
