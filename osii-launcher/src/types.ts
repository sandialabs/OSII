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
  stackImages?: StackImages | null;
  toolImages?: Record<string, string>;
  readableWiki: boolean;
  conceptEntityWiki: boolean;
  tesseractOpenCv: boolean;
}

export interface StackImages {
  release: string;
  core: string;
  dashboard: string;
  baselineProcessors: string;
}

export interface CatalogVersion { label: string; reference: string; }
export interface CatalogStack { id: string; displayName: string; images: StackImages; }
export interface CatalogTool { id: string; displayName: string; description: string; processorApi: boolean; versions: CatalogVersion[]; }
export interface CatalogImage { id: string; displayName: string; description: string; versions: CatalogVersion[]; }
export interface Catalog { version: number; registry: string; namespace: string; stacks: CatalogStack[]; tools: CatalogTool[]; images: CatalogImage[]; }
export interface CatalogResponse { catalog: Catalog; source: string; fetchedAt: number; cacheAgeSeconds: number | null; warning: string | null; }
export interface LocalImage { reference: string; present: boolean; id: string | null; digest: string | null; size: string | null; }
export interface ImageInventory { images: LocalImage[]; }
export interface ActivityRecord { id: string; label: string; command: string; timestamp: number; output: string; exitCode: number | null; running: boolean; }
export interface CustomMount { source: string; destination: string; readOnly: boolean; }
export interface CustomContainerDraft { id: string; name: string; image: string; command: string; arguments: string[]; environment: Record<string, string>; secretEnvironment: Record<string, string>; ports: string[]; mounts: CustomMount[]; network: string; restartPolicy: string; }
export interface ManagedContainer { id: string; name: string; image: string; state: string; status: string; }

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
