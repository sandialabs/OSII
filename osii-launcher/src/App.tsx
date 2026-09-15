import { useCallback, useEffect, useMemo, useState } from "react";
import { launcherApi } from "./launcherApi";
import type {
  DeploymentPreview,
  DeploymentStatus,
  ModelDiscovery,
  PodmanStatus,
  Profile,
  ProfileDraft,
  RegistryStatus,
  SourceCheck,
} from "./types";
import { coreImage, profileProblem, suggestedModels } from "./validation";

const emptyDraft: ProfileDraft = {
  name: "My OSII library",
  sourceDir: "",
  imagePrefix: import.meta.env.VITE_OSII_IMAGE_PREFIX ?? "",
  imageTag: import.meta.env.VITE_OSII_IMAGE_TAG ?? "",
  openaiBaseUrl: import.meta.env.VITE_OSII_OPENAI_BASE_URL ?? "",
  openaiEmbeddingModel: import.meta.env.VITE_OSII_OPENAI_EMBEDDING_MODEL ?? "",
  openaiChatModel: import.meta.env.VITE_OSII_OPENAI_CHAT_MODEL ?? "",
};

const stopped: DeploymentStatus = {
  profileId: null,
  state: "stopped",
  dashboardReady: false,
  apiReady: false,
  message: "OSII is not running.",
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`status-dot ${ok ? "good" : "waiting"}`} aria-hidden="true" />;
}

type CheckState = "idle" | "checking" | "verified" | "failed";

function StepStatus({ state, verifiedText }: { state: CheckState; verifiedText: string }) {
  const label = {
    idle: "Not checked",
    checking: "Checking…",
    verified: verifiedText,
    failed: "Check failed",
  }[state];
  return <span className={`pill ${state}`}>{label}</span>;
}

function App() {
  const [podman, setPodman] = useState<PodmanStatus | null>(null);
  const [registryHost, setRegistryHost] = useState(import.meta.env.VITE_OSII_REGISTRY ?? "quay.io");
  const [registry, setRegistry] = useState<RegistryStatus | null>(null);
  const [registryCheckState, setRegistryCheckState] = useState<CheckState>("idle");
  const [registryUsername, setRegistryUsername] = useState("");
  const [registryPassword, setRegistryPassword] = useState("");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProfileDraft>(emptyDraft);
  const [apiKey, setApiKey] = useState("");
  const [sourceCheck, setSourceCheck] = useState<SourceCheck | null>(null);
  const [sourceCheckState, setSourceCheckState] = useState<CheckState>("idle");
  const [modelDiscovery, setModelDiscovery] = useState<ModelDiscovery | null>(null);
  const [modelCheckState, setModelCheckState] = useState<CheckState>("idle");
  const [deployment, setDeployment] = useState<DeploymentStatus>(stopped);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [deploymentPreview, setDeploymentPreview] = useState<DeploymentPreview | null>(null);
  const [logs, setLogs] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("Checking this workstation…");
  const [problem, setProblem] = useState<string | null>(null);
  const [saveAttempted, setSaveAttempted] = useState(false);

  const selected = useMemo(
    () => profiles.find((profile) => profile.id === selectedId) ?? null,
    [profiles, selectedId],
  );
  const validation = profileProblem(draft);
  const runningSelected = deployment.profileId === selectedId && deployment.state !== "stopped";

  const run = useCallback(async <T,>(label: string, operation: () => Promise<T>): Promise<T | null> => {
    setBusy(label);
    setProblem(null);
    try {
      return await operation();
    } catch (error) {
      setProblem(errorMessage(error));
      return null;
    } finally {
      setBusy(null);
    }
  }, []);

  const refresh = useCallback(async () => {
    const [podmanResult, profileResult, deploymentResult] = await Promise.allSettled([
      launcherApi.checkPodman(),
      launcherApi.listProfiles(),
      launcherApi.deploymentStatus(),
    ]);
    if (podmanResult.status === "fulfilled") setPodman(podmanResult.value);
    if (profileResult.status === "fulfilled") {
      setProfiles(profileResult.value);
      if (!selectedId && profileResult.value.length) {
        const profile = profileResult.value[0];
        setSelectedId(profile.id);
        setDraft(profile);
      }
    }
    if (deploymentResult.status === "fulfilled") setDeployment(deploymentResult.value);
    setNotice("Ready for setup.");
  }, [selectedId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (deployment.state === "stopped") return;
    const timer = window.setInterval(() => {
      void launcherApi.deploymentStatus().then(setDeployment).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [deployment.state]);

  function update<K extends keyof ProfileDraft>(field: K, value: ProfileDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
    if (field === "sourceDir" || field === "imagePrefix" || field === "imageTag") {
      setSourceCheck(null);
      setSourceCheckState("idle");
    }
    if (field === "openaiBaseUrl") {
      setModelDiscovery(null);
      setModelCheckState("idle");
    }
  }

  function selectProfile(profile: Profile) {
    setSelectedId(profile.id);
    setDraft(profile);
    setApiKey("");
    setSourceCheck(null);
    setSourceCheckState("idle");
    setModelDiscovery(null);
    setModelCheckState("idle");
    setSaveAttempted(false);
    setAdvancedOpen(false);
    setDeploymentPreview(null);
    setLogs("");
  }

  const loadAdvanced = useCallback(async () => {
    if (!selectedId) {
      setDeploymentPreview(null);
      return;
    }
    try {
      const preview = await launcherApi.deploymentPreview(selectedId, Boolean(apiKey));
      setDeploymentPreview(preview);
    } catch (error) {
      setProblem(errorMessage(error));
    }
  }, [apiKey, selectedId]);

  async function toggleAdvanced() {
    const opening = !advancedOpen;
    setAdvancedOpen(opening);
    if (opening) await loadAdvanced();
  }

  async function save() {
    setSaveAttempted(true);
    if (validation) {
      setProblem(validation);
      return;
    }
    const saved = await run("Saving library", () => launcherApi.saveProfile(draft, selectedId ?? undefined));
    if (!saved) return;
    setSelectedId(saved.id);
    setProfiles((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
    setDraft(saved);
    setSaveAttempted(false);
    setDeploymentPreview(null);
    setNotice("Library settings saved.");
  }

  async function chooseSource() {
    const path = await run("Choosing source folder", launcherApi.chooseSource);
    if (path) update("sourceDir", path);
  }

  async function checkSource() {
    if (!draft.sourceDir.trim()) {
      setProblem("Choose a source folder first.");
      setSourceCheckState("failed");
      return;
    }
    setSourceCheckState("checking");
    const result = await run("Checking folder access", () =>
      launcherApi.validateSource(draft.sourceDir, coreImage(draft)),
    );
    if (result) {
      setSourceCheck(result);
      setSourceCheckState(result.ok ? "verified" : "failed");
      setNotice(result.message);
    } else {
      setSourceCheckState("failed");
    }
  }

  async function checkRegistry() {
    setRegistryCheckState("checking");
    const result = await run("Checking Quay login", () => launcherApi.registryStatus(registryHost));
    if (result) {
      setRegistry(result);
      setRegistryCheckState(result.loggedIn ? "verified" : "failed");
    } else {
      setRegistryCheckState("failed");
    }
  }

  async function loginRegistry() {
    setRegistryCheckState("checking");
    const result = await run("Logging into Quay", () =>
      launcherApi.loginRegistry(registryHost, registryUsername, registryPassword),
    );
    setRegistryPassword("");
    if (result) {
      setRegistry(result);
      setRegistryCheckState(result.loggedIn ? "verified" : "failed");
    } else {
      setRegistryCheckState("failed");
    }
  }

  async function discoverModels() {
    if (!draft.openaiBaseUrl.trim()) {
      setProblem("Enter the corporate OpenAI-compatible endpoint first.");
      setModelCheckState("failed");
      return;
    }
    if (!apiKey) {
      setProblem("Paste the model API key before checking available models.");
      setModelCheckState("failed");
      return;
    }
    setModelCheckState("checking");
    const result = await run("Checking model API", () =>
      launcherApi.discoverModels(draft.openaiBaseUrl, apiKey),
    );
    if (!result) {
      setModelCheckState("failed");
      return;
    }
    const defaults = suggestedModels(
      result.models,
      draft.openaiEmbeddingModel,
      draft.openaiChatModel,
    );
    setDraft((current) => ({
      ...current,
      openaiEmbeddingModel: defaults.embedding,
      openaiChatModel: defaults.chat,
    }));
    setModelDiscovery(result);
    setModelCheckState("verified");
    setNotice(result.message);
  }

  async function start() {
    if (!selectedId) {
      setProblem("Save this library before starting OSII.");
      return;
    }
    if (selected?.openaiBaseUrl && !apiKey) {
      setProblem("Paste the model API key before starting OSII.");
      return;
    }
    const result = await run("Starting OSII", () => launcherApi.startProfile(selectedId, apiKey));
    if (result) {
      setDeployment(result);
      setNotice(result.message);
      if (advancedOpen) await loadAdvanced();
    } else {
      setAdvancedOpen(true);
      await loadAdvanced();
    }
  }

  async function stop() {
    if (!selectedId) return;
    const result = await run("Stopping OSII", () => launcherApi.stopProfile(selectedId));
    if (result) {
      setDeployment(result);
      setNotice(result.message);
    }
  }

  async function fetchLogs() {
    if (!selectedId) return;
    const result = await run("Reading service logs", () => launcherApi.logs(selectedId));
    if (result !== null) setLogs(result);
  }

  const workstationReady = Boolean(podman?.engineReady && podman.composeReady);
  return (
    <main>
      <header className="hero">
        <div className="brand-lockup">
          <div className="brand-mark" role="img" aria-label="Corporate logo placeholder">🔍</div>
          <div>
            <p className="eyebrow">OSII workstation</p>
            <h1>OSII: the on store intelligence index</h1>
            <p className="lede">
              Your research library, ready locally. Connect a folder, choose the approved container release, and let OSII manage the services.
            </p>
          </div>
        </div>
        <div className={`overall-status ${deployment.state}`}>
          <StatusDot ok={deployment.state === "running"} />
          <div>
            <strong>{deployment.state === "running" ? "OSII is ready" : deployment.state === "starting" ? "Starting OSII" : "Setup mode"}</strong>
            <span>{notice}</span>
          </div>
        </div>
      </header>

      {problem && <div className="alert" role="alert"><strong>Needs attention</strong><span>{problem}</span></div>}

      <section className="workspace-grid">
        <aside className="sidebar panel">
          <div className="panel-heading">
            <div><p className="step-label">Libraries</p><h2>Saved profiles</h2></div>
            <button className="icon-button" title="New library" onClick={() => {
              setSelectedId(null);
              setDraft(emptyDraft);
              setApiKey("");
              setSourceCheck(null);
              setSourceCheckState("idle");
              setModelDiscovery(null);
              setModelCheckState("idle");
              setSaveAttempted(false);
              setAdvancedOpen(false);
              setDeploymentPreview(null);
            }}>+</button>
          </div>
          <div className="profile-list">
            {profiles.length === 0 && <p className="empty">Your first saved library will appear here.</p>}
            {profiles.map((profile) => (
              <button
                className={`profile-row ${profile.id === selectedId ? "selected" : ""}`}
                key={profile.id}
                onClick={() => selectProfile(profile)}
              >
                <span>{profile.name}</span>
                <small>{profile.sourceDir}</small>
              </button>
            ))}
          </div>

          <div className="readiness">
            <p className="step-label">Workstation</p>
            <div className="readiness-row"><StatusDot ok={Boolean(podman?.installed)} /><span>Podman installed</span></div>
            <div className="readiness-row"><StatusDot ok={Boolean(podman?.engineReady)} /><span>Container engine ready</span></div>
            <div className="readiness-row"><StatusDot ok={Boolean(podman?.composeReady)} /><span>Compose ready</span></div>
            <p className="technical-note">{podman?.message ?? "Checking Podman…"}</p>
            <div className="button-row">
              <button className="secondary" disabled={Boolean(busy)} onClick={() => void run("Checking Podman", async () => {
                const result = await launcherApi.checkPodman();
                setPodman(result);
                return result;
              })}>Check again</button>
              {podman?.installed && !podman.engineReady && (
                <button disabled={Boolean(busy)} onClick={() => void run("Preparing Podman", async () => {
                  const result = await launcherApi.prepareMachine();
                  setPodman(result);
                  return result;
                })}>Prepare</button>
              )}
            </div>
          </div>
        </aside>

        <div className="content-stack">
          <section className="panel section-card">
            <div className="section-number">1</div>
            <div className="section-body">
              <div className="section-title"><div><p className="step-label">Approved images</p><h2>Connect to Quay</h2></div><StepStatus state={registryCheckState} verifiedText={registry?.username ? `Connected as ${registry.username}` : "Connected"} /></div>
              <p className="section-copy">The launcher passes this credential directly to Podman. It never stores or reads the registry password.</p>
              <div className="form-grid registry-grid">
                <label>Registry<input value={registryHost} onChange={(event) => {
                  setRegistryHost(event.target.value);
                  setRegistry(null);
                  setRegistryCheckState("idle");
                }} placeholder="quay.corp.example" /></label>
                <label>Username<input value={registryUsername} onChange={(event) => setRegistryUsername(event.target.value)} autoComplete="username" /></label>
                <label>Robot token or password<input type="password" value={registryPassword} onChange={(event) => setRegistryPassword(event.target.value)} autoComplete="current-password" /></label>
              </div>
              <div className="button-row">
                <button className="secondary" disabled={Boolean(busy) || !registryHost.trim()} onClick={() => void checkRegistry()}>Check login</button>
                <button disabled={Boolean(busy) || !registryHost.trim() || !registryUsername.trim() || !registryPassword} onClick={() => void loginRegistry()}>Log in</button>
              </div>
            </div>
          </section>

          <section className="panel section-card">
            <div className="section-number">2</div>
            <div className="section-body">
              <div className="section-title"><div><p className="step-label">Library profile</p><h2>Choose what OSII may read</h2></div><StepStatus state={sourceCheckState} verifiedText="Folder verified" /></div>
              <div className="form-grid">
                <label>Library name<input value={draft.name} onChange={(event) => update("name", event.target.value)} /></label>
                <label className="wide">Shared-drive or local folder<div className="input-action"><input value={draft.sourceDir} onChange={(event) => update("sourceDir", event.target.value)} placeholder="Choose a folder" /><button className="secondary" onClick={() => void chooseSource()}>Browse</button></div></label>
                <label>Quay image prefix<input value={draft.imagePrefix} onChange={(event) => update("imagePrefix", event.target.value)} placeholder="quay.corp.example/team/osii" /></label>
                <label>Release tag<input value={draft.imageTag} onChange={(event) => update("imageTag", event.target.value)} placeholder="2026.09.14" /></label>
              </div>
              <div className="button-row">
                <button className="secondary" disabled={Boolean(busy) || !workstationReady} onClick={() => void checkSource()}>Test container access</button>
              </div>
              {sourceCheck && <p className={`check-detail ${sourceCheck.ok ? "ok" : "bad"}`}>{sourceCheck.message}</p>}
            </div>
          </section>

          <section className="panel section-card">
            <div className="section-number">3</div>
            <div className="section-body">
              <div className="section-title"><div><p className="step-label">Models</p><h2>Corporate models first, Ollama as fallback</h2></div><StepStatus state={modelCheckState} verifiedText="Models verified" /></div>
              <p className="section-copy">Enter the endpoint and key, then let OSII list the available models. It prefers a MiniLM embedding model and Gemma 4 for chat when those names are available. Leave the endpoint blank for local Ollama only.</p>
              <div className="form-grid">
                <label className="wide">OpenAI-compatible endpoint<input value={draft.openaiBaseUrl} onChange={(event) => update("openaiBaseUrl", event.target.value)} placeholder="https://models.corp.example/v1" /></label>
                <label>Embedding model<input list="available-models" value={draft.openaiEmbeddingModel} onChange={(event) => update("openaiEmbeddingModel", event.target.value)} placeholder="Selected after model check" /></label>
                <label>Chat model<input list="available-models" value={draft.openaiChatModel} onChange={(event) => update("openaiChatModel", event.target.value)} placeholder="Selected after model check" /></label>
                <datalist id="available-models">
                  {modelDiscovery?.models.map((model) => <option value={model} key={model} />)}
                </datalist>
                <label className="wide">API key — session only<input type="password" value={apiKey} onChange={(event) => {
                  setApiKey(event.target.value);
                  setModelDiscovery(null);
                  setModelCheckState("idle");
                }} autoComplete="off" placeholder="Paste again each time you open the launcher" /></label>
              </div>
              <div className="button-row">
                <button className="secondary" disabled={Boolean(busy) || !draft.openaiBaseUrl.trim() || !apiKey} onClick={() => void discoverModels()}>{busy === "Checking model API" ? "Checking…" : "Find available models"}</button>
                <button disabled={Boolean(busy)} onClick={() => void save()}>{busy === "Saving library" ? "Saving…" : "Save library"}</button>
              </div>
              {modelDiscovery && <p className="check-detail ok">{modelDiscovery.message}</p>}
              <p className="secure-note">The launcher keeps this key only in memory for the current session. It is not saved in the profile or operating-system credential store.</p>
              {saveAttempted && validation && <div className="form-error" role="alert"><strong>Library not saved.</strong> {validation}</div>}
            </div>
          </section>

          <section className="panel launch-card">
            <div>
              <p className="step-label">Deployment</p>
              <h2>{selected ? `Run ${selected.name}` : "Save a library to continue"}</h2>
              <p>{deployment.message}</p>
            </div>
            <div className="launch-actions">
              {!runningSelected ? (
                <button className="primary-large" disabled={Boolean(busy) || !selectedId || !workstationReady} onClick={() => void start()}>{busy === "Starting OSII" ? "Starting…" : "Start OSII"}</button>
              ) : (
                <>
                  <button className="primary-large" disabled={!deployment.dashboardReady} onClick={() => void launcherApi.openDashboard()}>Open dashboard</button>
                  <button className="secondary" disabled={Boolean(busy)} onClick={() => void stop()}>Stop</button>
                </>
              )}
              {selectedId && <button className="text-button" disabled={Boolean(busy)} onClick={() => void fetchLogs()}>View recent logs</button>}
              {selectedId && <button className="text-button" disabled={Boolean(busy)} onClick={() => void toggleAdvanced()}>{advancedOpen ? "Hide advanced" : "Advanced view"}</button>}
            </div>
          </section>

          {advancedOpen && (
            <section className="panel advanced-diagnostics">
              <div className="panel-heading">
                <div><p className="step-label">Advanced</p><h2>Deployment preview</h2></div>
                <button className="secondary" disabled={!selectedId} onClick={() => void loadAdvanced()}>Refresh</button>
              </div>
              {!deploymentPreview ? (
                <p className="empty">Save and select a library to generate its deployment preview.</p>
              ) : (
                <div className="advanced-content">
                  <p className="technical-note">This is the saved profile OSII will run. Credentials are never shown; secret input is marked as redacted.</p>
                  <section>
                    <h3>Queued start commands</h3>
                    <ol className="command-list">
                      {deploymentPreview.commands.map((command, index) => <li key={`${index}-${command}`}><code>{command}</code></li>)}
                    </ol>
                  </section>
                  <section>
                    <h3>Compose environment</h3>
                    <p className="diagnostic-path">{deploymentPreview.environmentPath}</p>
                    <pre>{deploymentPreview.environment}</pre>
                  </section>
                  <section>
                    <h3>Compose override</h3>
                    <p className="diagnostic-path">{deploymentPreview.overridePath}</p>
                    <pre>{deploymentPreview.composeOverride}</pre>
                  </section>
                  {problem && <section><h3>Latest error</h3><pre className="error-output">{problem}</pre></section>}
                </div>
              )}
            </section>
          )}

          {logs && <section className="panel logs"><div className="panel-heading"><div><p className="step-label">Diagnostics</p><h2>Recent service logs</h2></div><button className="icon-button" onClick={() => setLogs("")}>×</button></div><pre>{logs}</pre></section>}
        </div>
      </section>
    </main>
  );
}

export default App;
