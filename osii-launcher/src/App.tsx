import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { launcherApi } from "./launcherApi";
import type {
  DeploymentPreview,
  DeploymentStatus,
  PodmanStatus,
  Profile,
  ProfileDraft,
  RegistryStatus,
  SourceCheck,
} from "./types";
import { coreImage, profileImages, profileProblem } from "./validation";

const emptyDraft: ProfileDraft = {
  name: "My OSII library",
  sourceDir: "",
  imagePrefix: import.meta.env.VITE_OSII_IMAGE_PREFIX ?? "",
  imageTag: import.meta.env.VITE_OSII_IMAGE_TAG ?? "",
  readableWiki: false,
  conceptEntityWiki: false,
  tesseractOpenCv: false,
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
  const [sourceCheck, setSourceCheck] = useState<SourceCheck | null>(null);
  const [sourceCheckState, setSourceCheckState] = useState<CheckState>("idle");
  const [deployment, setDeployment] = useState<DeploymentStatus>(stopped);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [deploymentPreview, setDeploymentPreview] = useState<DeploymentPreview | null>(null);
  const [logs, setLogs] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("Checking this workstation…");
  const [problem, setProblem] = useState<string | null>(null);
  const [saveAttempted, setSaveAttempted] = useState(false);
  const saveInFlight = useRef(false);

  const selected = useMemo(
    () => profiles.find((profile) => profile.id === selectedId) ?? null,
    [profiles, selectedId],
  );
  const validation = profileProblem(draft);
  const runningSelected = deployment.profileId === selectedId && deployment.state !== "stopped";
  const plannedImages = profileImages(draft);
  const imageRecoveryCommands = selected ? [
    `podman login ${registryHost.trim()}`,
    ...profileImages(selected).map((image) => `podman pull ${image}`),
  ].join("\n") : "";

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
  }

  function selectProfile(profile: Profile) {
    setSelectedId(profile.id);
    setDraft(profile);
    setSourceCheck(null);
    setSourceCheckState("idle");
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
      const preview = await launcherApi.deploymentPreview(selectedId);
      setDeploymentPreview(preview);
    } catch (error) {
      setProblem(errorMessage(error));
    }
  }, [selectedId]);

  async function toggleAdvanced() {
    const opening = !advancedOpen;
    setAdvancedOpen(opening);
    if (opening) await loadAdvanced();
  }

  async function save() {
    if (saveInFlight.current) return;
    saveInFlight.current = true;
    setSaveAttempted(true);
    try {
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
    } finally {
      saveInFlight.current = false;
    }
  }

  async function removeSelectedProfile() {
    if (!selected) return;
    if (!window.confirm(`Remove the saved profile “${selected.name}”? Your source folder and OSII library data will not be deleted.`)) return;
    const remaining = await run("Removing library profile", () => launcherApi.deleteProfile(selected.id));
    if (!remaining) return;
    setProfiles(remaining);
    const next = remaining[0] ?? null;
    setSelectedId(next?.id ?? null);
    setDraft(next ?? emptyDraft);
    setAdvancedOpen(false);
    setDeploymentPreview(null);
    setLogs("");
    setNotice("Saved profile removed. Library files were preserved.");
  }

  async function exportSelectedProfile() {
    if (!selected) return;
    const destination = await launcherApi.chooseProfileExport(selected.name.replace(/[^a-z0-9-]+/gi, "-").toLowerCase());
    if (!destination) return;
    const done = await run("Exporting profile", () => launcherApi.exportProfile(selected.id, destination));
    if (done !== null) setNotice("Profile exported without API keys or library data. The file contains source paths and service URLs.");
  }

  async function importSavedProfile() {
    const source = await launcherApi.chooseProfileImport();
    if (typeof source !== "string") return;
    const imported = await run("Importing profile", () => launcherApi.importProfile(source));
    if (!imported) return;
    setProfiles((current) => [imported, ...current]);
    selectProfile(imported);
    setNotice("Profile imported. Confirm the source path and service connections; API keys were not imported.");
  }

  async function chooseSource() {
    const path = await run("Choosing source folder", launcherApi.chooseSource);
    if (path) update("sourceDir", path);
  }

  async function prepareDemo() {
    if (!draft.imagePrefix.trim() || !draft.imageTag.trim()) {
      setProblem("Set the Quay image prefix and pinned release tag before loading the built-in demo.");
      return;
    }
    const profile = await run("Preparing built-in demo", () =>
      launcherApi.prepareDemoProfile(draft.imagePrefix, draft.imageTag),
    );
    if (!profile) return;
    setProfiles((current) => [profile, ...current.filter((item) => item.id !== profile.id)]);
    selectProfile(profile);
    setNotice("Built-in demo is ready. Start OSII with local images, or log into Quay to pull missing ones.");
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

  async function start() {
    if (!selectedId) {
      setProblem("Save this library before starting OSII.");
      return;
    }
    const result = await run("Starting OSII", () => launcherApi.startProfile(selectedId));
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
              setSourceCheck(null);
              setSourceCheckState("idle");
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
            {selected && (
              <button className="text-button danger remove-profile" disabled={Boolean(busy) || runningSelected} onClick={() => void removeSelectedProfile()}>
                Remove selected
              </button>
            )}
            <div className="button-row">
              <button className="secondary" disabled={Boolean(busy)} onClick={() => void importSavedProfile()}>Import profile</button>
              {selected && <button className="secondary" disabled={Boolean(busy)} onClick={() => void exportSelectedProfile()}>Export profile</button>}
            </div>
            <p className="technical-note">Exports omit keys and library data, but include exact source paths and service URLs.</p>
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
              <div className="section-title"><div><p className="step-label">Approved images</p><h2>Images and registry</h2></div><StepStatus state={registryCheckState} verifiedText={registry?.username ? `Connected as ${registry.username}` : "Connected"} /></div>
              <p className="section-copy">Already loaded images work offline. Log in only if OSII needs to pull missing images; the launcher passes credentials directly to Podman and does not store the password.</p>
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
              <details className="image-plan">
                <summary>Images needed when OSII starts{plannedImages.length ? ` (${plannedImages.length})` : ""}</summary>
                <p>Checking Quay verifies an existing Podman login. <strong>Start OSII</strong> uses loaded images and pulls only missing ones. An offline image collection can be loaded first with <code>podman load</code>.</p>
                {plannedImages.length ? (
                  <ul>{plannedImages.map((image) => <li key={image}><code>{image}</code></li>)}</ul>
                ) : (
                  <p>Enter the image prefix and pinned release tag in step 2 to preview the approved images.</p>
                )}
              </details>
            </div>
          </section>

          <section className="panel section-card">
            <div className="section-number">2</div>
            <div className="section-body">
              <div className="section-title"><div><p className="step-label">Library profile</p><h2>Choose what OSII may read</h2></div><StepStatus state={sourceCheckState} verifiedText="Folder verified" /></div>
              <p className="section-copy">OSII reads this folder but never changes its original files. For a shared drive, connect it in Finder or Windows Explorer first, then paste its mounted, mapped-drive, or UNC path here. The Browse window selects folders that are already available; it does not sign in to or mount network shares.</p>
              <div className="form-grid">
                <label>Library name<input value={draft.name} onChange={(event) => update("name", event.target.value)} /></label>
                <label className="wide">Document folder — local or already-connected shared drive<div className="input-action"><input value={draft.sourceDir} onChange={(event) => update("sourceDir", event.target.value)} placeholder={"e.g. /Volumes/Team Documents, S:\\Team Documents, or \\\\server\\share\\folder"} /><button className="secondary" onClick={() => void chooseSource()}>Browse mounted folder</button></div></label>
                <label>Quay image prefix<input value={draft.imagePrefix} onChange={(event) => update("imagePrefix", event.target.value)} placeholder="quay.corp.example/team/osii" /></label>
                <label>Release tag<input value={draft.imageTag} onChange={(event) => update("imageTag", event.target.value)} placeholder="2026.09.14" /></label>
              </div>
              <p className="source-note"><strong>Shared-drive setup:</strong> OSII does not store share credentials or mount shares. On Windows, open the share in Explorer or map a drive; on macOS, connect it in Finder so it appears under <code>/Volumes</code>. Then use <strong>Test container access</strong>. OSII mounts a verified source read-only inside its containers.</p>
              <div className="button-row">
                <button className="secondary" disabled={Boolean(busy) || !workstationReady} onClick={() => void checkSource()}>Test container access</button>
              </div>
              {sourceCheck && <p className={`check-detail ${sourceCheck.ok ? "ok" : "bad"}`}>{sourceCheck.message}</p>}
              <div className="demo-callout">
                <div>
                  <strong>Try the built-in demo</strong>
                  <p>Creates a separate local library with the Purcell PDF and bundled Iris and Wine scikit-learn sample datasets. It never changes your shared drive.</p>
                </div>
                <button className="secondary" disabled={Boolean(busy)} onClick={() => void prepareDemo()}>{busy === "Preparing built-in demo" ? "Preparing…" : "Load built-in demo"}</button>
              </div>
            </div>
          </section>

          <section className="panel section-card">
            <div className="section-number">3</div>
            <div className="section-body">
              <div className="section-title"><div><p className="step-label">Optional tools</p><h2>Choose extra processing services</h2></div></div>
              <p className="section-copy">The baseline works without these. Selected tools are pulled from Quay and started with this library; configure any language-model connections later in Workbench Setup.</p>
              <div className="tool-choice-list">
                <label><input type="checkbox" checked={draft.readableWiki} onChange={(event) => update("readableWiki", event.target.checked)} /><span><strong>Readable LLM Wiki</strong><small>Cited, reader-friendly Markdown. Uses a model connection chosen in Setup.</small></span></label>
                <label><input type="checkbox" checked={draft.conceptEntityWiki} onChange={(event) => update("conceptEntityWiki", event.target.checked)} /><span><strong>Concept and Entity LLM Wiki</strong><small>Produces a wiki, entity list, and sortable concept table.</small></span></label>
                <label><input type="checkbox" checked={draft.tesseractOpenCv} onChange={(event) => update("tesseractOpenCv", event.target.checked)} /><span><strong>Tesseract OCR with OpenCV regions</strong><small>Self-contained OCR with region and bounding-box provenance; no model connection.</small></span></label>
              </div>
              <div className="button-row">
                <button disabled={Boolean(busy)} onClick={() => void save()}>{busy === "Saving library" ? "Saving…" : "Save library"}</button>
              </div>
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
                  {selected && <section>
                    <h3>If a Quay pull fails</h3>
                    <p className="technical-note">On Windows, open PowerShell and run these commands in order. <code>podman login</code> prompts for your Quay credentials. After every displayed pull succeeds, return here and select <strong>Start OSII</strong>; do not run Compose directly because the launcher creates this library&apos;s mounts and configuration.</p>
                    <pre>{imageRecoveryCommands}</pre>
                  </section>}
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
