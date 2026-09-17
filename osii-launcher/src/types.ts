export interface PodmanStatus {
  installed: boolean;
  version: string | null;
  majorVersion: number | null;
  engineReady: boolean;
  composeReady: boolean;
  composeProvider: string | null;
  message: string;
}

export interface RegistryStatus {
  registry: string;
  loggedIn: boolean;
  username: string | null;
}

export interface ProfileDraft {
  name: string;
  sourceDir: string;
  imagePrefix: string;
  imageTag: string;
  readableWiki: boolean;
  conceptEntityWiki: boolean;
  tesseractOpenCv: boolean;
}

export interface Profile extends ProfileDraft {
  id: string;
}

export interface SourceCheck {
  ok: boolean;
  canonicalPath: string;
  containerVisible: boolean;
  message: string;
}

export interface DeploymentStatus {
  profileId: string | null;
  state: "stopped" | "starting" | "running" | "degraded";
  dashboardReady: boolean;
  apiReady: boolean;
  message: string;
}

export interface DeploymentPreview {
  environmentPath: string;
  environment: string;
  overridePath: string;
  composeOverride: string;
  commands: string[];
}
