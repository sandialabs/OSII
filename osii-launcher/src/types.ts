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
  openaiBaseUrl: string;
  openaiEmbeddingModel: string;
  openaiChatModel: string;
}

export interface Profile extends ProfileDraft {
  id: string;
  apiKeyPresent: boolean;
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
