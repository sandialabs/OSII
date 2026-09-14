import { useCallback, useEffect, useMemo, useState } from "react";
import { launcherApi } from "./launcherApi";
import type {
  DeploymentStatus,
  PodmanStatus,
  Profile,
  ProfileDraft,
  RegistryStatus,
  SourceCheck,
} from "./types";
import { coreImage, profileProblem } from "./validation";

const emptyDraft: ProfileDraft = {
  name: "My OSII library",
  sourceDir: "",
  imagePrefix: import.meta.env.VITE_OSII_IMAGE_PREFIX ?? "",
  imageTag: import.meta.env.VITE_OSII_IMAGE_TAG ?? "",
  openaiBaseUrl: "",
  openaiEmbeddingModel: "",
  openaiChatModel: "",
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

function App() {
  const [podman, setPodman] = useState<PodmanStatus | null>(null);
  const [registryHost, setRegistryHost] = useState(import.meta.env.VITE_OSII_REGISTRY ?? "quay.io");
  const [registry, setRegistry] = useState<RegistryStatus | null>(null);
  const [registryUsername, setRegistryUsername] = useState("");
  const [registryPassword, setRegistryPassword] = useState("");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProfileDraft>(emptyDraft);
  const [apiKey, setApiKey] = useState("");
  const [sourceCheck, setSourceCheck] = useState<SourceCheck | null>(null);
  const [deployment, setDeployment] = useState<DeploymentStatus>(stopped);
  const [logs, setLogs] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("Checking this workstation…");
  const [problem, setProblem] = useState<string | null>(null);

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
    }
  }

  function selectProfile(profile: Profile) {
    setSelectedId(profile.id);
    setDraft(profile);
    setApiKey("");
    setSourceCheck(null);
    setLogs("");
  }

  async function save() {
    if (validation) {
      setProblem(validation);
      return;
    }
    const saved = await run("Saving library", () => launcherApi.saveProfile(draft, selectedId ?? undefined));
    if (!saved) return;
    if (apiKey.trim()) {
      const stored = await run("Storing API key", () => launcherApi.storeApiKey(saved.id, apiKey.trim()));
      if (stored === null) return;
      saved.apiKeyPresent = true;
      setApiKey("");
    }
    setSelectedId(saved.id);
    setProfiles((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
    setDraft(saved);
    setNotice("Library settings saved.");
  }

  async function chooseSource() {
    const path = await run("Choosing source folder", launcherApi.chooseSource);
    if (path) update("sourceDir", path);
  }

  async function checkSource() {
    if (!draft.sourceDir.trim()) {
      setProblem("Choose a source folder first.");
      return;
    }
    const result = await run("Checking folder access", () =>
      launcherApi.validateSource(draft.sourceDir, coreImage(draft)),
    );
    if (result) {
      setSourceCheck(result);
      setNotice(result.message);
    }
  }

  async function start() {
    if (!selectedId) {
      setProblem("Save this library before starting OSII.");
      return;
    }
    const result = await run("Starting OSII", () => launcherApi.startProfile(selectedId));
    if (result) {
      setDeployment(result);
      setNotice(result.message);
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
        <div>
          <p className="eyebrow">OSII workstation</p>
          <h1>Your research library, ready locally.</h1>
          <p className="lede">
            Connect a folder, choose the approved container release, and let OSII manage the services.
          </p>
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
              <div className="section-title"><div><p className="step-label">Approved images</p><h2>Connect to Quay</h2></div>{registry?.loggedIn && <span className="pill">Connected as {registry.username}</span>}</div>
              <p className="section-copy">The launcher passes this credential directly to Podman. It never stores or reads the registry password.</p>
              <div className="form-grid registry-grid">
                <label>Registry<input value={registryHost} onChange={(event) => setRegistryHost(event.target.value)} placeholder="quay.corp.example" /></label>
                <label>Username<input value={registryUsername} onChange={(event) => setRegistryUsername(event.target.value)} autoComplete="username" /></label>
                <label>Robot token or password<input type="password" value={registryPassword} onChange={(event) => setRegistryPassword(event.target.value)} autoComplete="current-password" /></label>
              </div>
              <div className="button-row">
                <button className="secondary" disabled={Boolean(busy) || !registryHost.trim()} onClick={() => void run("Checking Quay login", async () => {
                  const result = await launcherApi.registryStatus(registryHost);
                  setRegistry(result);
                  return result;
                })}>Check login</button>
                <button disabled={Boolean(busy) || !registryHost.trim() || !registryUsername.trim() || !registryPassword} onClick={() => void run("Logging into Quay", async () => {
                  const result = await launcherApi.loginRegistry(registryHost, registryUsername, registryPassword);
                  setRegistryPassword("");
                  setRegistry(result);
                  return result;
                })}>Log in</button>
              </div>
            </div>
          </section>

          <section className="panel section-card">
            <div className="section-number">2</div>
            <div className="section-body">
              <div className="section-title"><div><p className="step-label">Library profile</p><h2>Choose what OSII may read</h2></div></div>
              <div className="form-grid">
                <label>Library name<input value={draft.name} onChange={(event) => update("name", event.target.value)} /></label>
                <label className="wide">Shared-drive or local folder<div className="input-action"><input value={draft.sourceDir} onChange={(event) => update("sourceDir", event.target.value)} placeholder="Choose a folder" /><button className="secondary" onClick={() => void chooseSource()}>Browse</button></div></label>
                <label>Quay image prefix<input value={draft.imagePrefix} onChange={(event) => update("imagePrefix", event.target.value)} placeholder="quay.corp.example/team/osii" /></label>
                <label>Release tag<input value={draft.imageTag} onChange={(event) => update("imageTag", event.target.value)} placeholder="2026.09.14" /></label>
              </div>
              <div className="button-row">
                <button className="secondary" disabled={Boolean(busy) || !workstationReady} onClick={() => void checkSource()}>Test container access</button>
                {sourceCheck && <span className={`inline-status ${sourceCheck.ok ? "ok" : "bad"}`}>{sourceCheck.message}</span>}
              </div>
            </div>
          </section>

          <section className="panel section-card">
            <div className="section-number">3</div>
            <div className="section-body">
              <div className="section-title"><div><p className="step-label">Models</p><h2>Corporate models first, Ollama as fallback</h2></div>{selected?.apiKeyPresent && <span className="pill">API key stored securely</span>}</div>
              <p className="section-copy">Leave these blank for local Ollama only. API keys go to the operating-system credential store, not a project file.</p>
              <div className="form-grid">
                <label className="wide">OpenAI-compatible endpoint<input value={draft.openaiBaseUrl} onChange={(event) => update("openaiBaseUrl", event.target.value)} placeholder="https://models.corp.example/v1" /></label>
                <label>Embedding model<input value={draft.openaiEmbeddingModel} onChange={(event) => update("openaiEmbeddingModel", event.target.value)} placeholder="approved embedding model" /></label>
                <label>Chat model<input value={draft.openaiChatModel} onChange={(event) => update("openaiChatModel", event.target.value)} placeholder="approved chat model" /></label>
                <label className="wide">API key<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="new-password" placeholder={selected?.apiKeyPresent ? "Stored — enter a replacement only" : "Optional"} /></label>
              </div>
              <div className="button-row">
                <button disabled={Boolean(busy) || Boolean(validation)} onClick={() => void save()}>{busy === "Saving library" ? "Saving…" : "Save library"}</button>
                {selected?.apiKeyPresent && <button className="text-button danger" disabled={Boolean(busy)} onClick={() => void run("Removing API key", async () => {
                  await launcherApi.forgetApiKey(selected.id);
                  const updated = { ...selected, apiKeyPresent: false };
                  setProfiles((current) => current.map((item) => item.id === updated.id ? updated : item));
                  return true;
                })}>Forget stored key</button>}
                {validation && <span className="inline-status bad">{validation}</span>}
              </div>
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
            </div>
          </section>

          {logs && <section className="panel logs"><div className="panel-heading"><div><p className="step-label">Diagnostics</p><h2>Recent service logs</h2></div><button className="icon-button" onClick={() => setLogs("")}>×</button></div><pre>{logs}</pre></section>}
        </div>
      </section>
    </main>
  );
}

export default App;
