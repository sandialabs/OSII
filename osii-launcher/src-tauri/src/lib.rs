use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem};
use tauri::path::BaseDirectory;
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

const BASELINE_SERVICES: &[&str] = &[
    "tesseract",
    "local-extractor",
    "local-synthesizer",
    "local-embedder",
    "local-enricher",
    "model-provider-bridge",
    "api",
    "worker",
    "dashboard",
];

const DEMO_PROFILE_ID: &str = "osii-demo";
const DEMO_PROFILE_NAME: &str = "OSII built-in demo";

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct PodmanStatus {
    installed: bool,
    version: Option<String>,
    major_version: Option<u32>,
    engine_ready: bool,
    compose_ready: bool,
    compose_provider: Option<String>,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RegistryStatus {
    registry: String,
    logged_in: bool,
    username: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProfileDraft {
    name: String,
    source_dir: String,
    image_prefix: String,
    image_tag: String,
    #[serde(default)]
    stack_images: Option<StackImages>,
    #[serde(default)]
    tool_images: BTreeMap<String, String>,
    #[serde(default)]
    readable_wiki: bool,
    #[serde(default)]
    concept_entity_wiki: bool,
    #[serde(default)]
    tesseract_open_cv: bool,
}

#[derive(Debug, Serialize, Deserialize)]
struct ProfileSnapshot {
    version: u32,
    profile: ProfileDraft,
    model_config: toml::Value,
    tool_config: toml::Value,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct Profile {
    id: String,
    name: String,
    source_dir: String,
    image_prefix: String,
    image_tag: String,
    #[serde(default)]
    stack_images: Option<StackImages>,
    #[serde(default)]
    tool_images: BTreeMap<String, String>,
    #[serde(default)]
    readable_wiki: bool,
    #[serde(default)]
    concept_entity_wiki: bool,
    #[serde(default)]
    tesseract_open_cv: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
struct StackImages {
    release: String,
    core: String,
    dashboard: String,
    baseline_processors: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogVersion {
    label: String,
    reference: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogTool {
    id: String,
    display_name: String,
    #[serde(default)]
    description: String,
    #[serde(default)]
    processor_api: bool,
    versions: Vec<CatalogVersion>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogImage {
    id: String,
    display_name: String,
    #[serde(default)]
    description: String,
    versions: Vec<CatalogVersion>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogStack {
    id: String,
    display_name: String,
    images: StackImages,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct Catalog {
    version: u32,
    registry: String,
    namespace: String,
    stacks: Vec<CatalogStack>,
    #[serde(default)]
    tools: Vec<CatalogTool>,
    #[serde(default)]
    images: Vec<CatalogImage>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogResponse {
    catalog: Catalog,
    source: String,
    fetched_at: u64,
    cache_age_seconds: Option<u64>,
    warning: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct LocalImage {
    reference: String,
    present: bool,
    id: Option<String>,
    digest: Option<String>,
    size: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ImageInventory {
    images: Vec<LocalImage>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ActivityRecord {
    id: String,
    label: String,
    command: String,
    timestamp: u64,
    output: String,
    exit_code: Option<i32>,
    running: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct CustomContainerDraft {
    #[serde(default)]
    id: String,
    name: String,
    image: String,
    #[serde(default)]
    command: String,
    #[serde(default)]
    arguments: Vec<String>,
    #[serde(default)]
    environment: BTreeMap<String, String>,
    #[serde(default)]
    secret_environment: BTreeMap<String, String>,
    #[serde(default)]
    ports: Vec<String>,
    #[serde(default)]
    mounts: Vec<CustomMount>,
    #[serde(default)]
    network: String,
    #[serde(default)]
    restart_policy: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct CustomMount {
    source: String,
    destination: String,
    #[serde(default)]
    read_only: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ManagedContainer {
    id: String,
    name: String,
    image: String,
    state: String,
    status: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SourceCheck {
    ok: bool,
    canonical_path: String,
    container_visible: bool,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DeploymentStatus {
    profile_id: Option<String>,
    state: String,
    dashboard_ready: bool,
    api_ready: bool,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DeploymentPreview {
    environment_path: String,
    environment: String,
    override_path: String,
    compose_override: String,
    commands: Vec<String>,
}

struct DeploymentFiles {
    environment_path: PathBuf,
    environment: String,
    override_path: PathBuf,
    compose_override: String,
}

#[derive(Debug, Clone, Copy)]
enum ComposeProvider {
    PodmanCompose,
    PodmanPlugin,
}

fn output_text(output: &Output) -> String {
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if stderr.is_empty() {
        stdout
    } else {
        stderr
    }
}

fn unix_timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn redact(value: &str, secrets: &[String]) -> String {
    secrets.iter().fold(value.to_string(), |text, secret| {
        if secret.is_empty() { text } else { text.replace(secret, "[REDACTED]") }
    })
}

fn activity_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(launcher_data_dir(app)?.join("activity.json"))
}

fn append_activity(app: &AppHandle, record: &ActivityRecord) {
    let path = match activity_path(app) { Ok(path) => path, Err(_) => return };
    let mut records: Vec<ActivityRecord> = fs::read_to_string(&path)
        .ok()
        .and_then(|value| serde_json::from_str(&value).ok())
        .unwrap_or_default();
    records.push(record.clone());
    if records.len() > 120 { records.drain(..records.len() - 120); }
    if let Ok(value) = serde_json::to_string_pretty(&records) {
        let _ = fs::write(path, format!("{value}\n"));
    }
}

fn emit_activity(app: &AppHandle, record: &ActivityRecord) {
    let _ = app.emit("osii://activity", record);
}

fn run_activity(
    app: &AppHandle,
    label: &str,
    program: &str,
    arguments: &[String],
    secrets: &[String],
) -> Result<Output, String> {
    let id = uuid::Uuid::new_v4().to_string();
    let command = redact(&display_command(&program_path(program), arguments), secrets);
    let started = ActivityRecord {
        id: id.clone(), label: label.to_string(), command: command.clone(), timestamp: unix_timestamp(),
        output: String::new(), exit_code: None, running: true,
    };
    emit_activity(app, &started);
    let mut child = process_command(program_path(program))
        .args(arguments)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("Could not run {program}: {error}"))?;
    let stdout = child.stdout.take().ok_or_else(|| format!("Could not read {program} output"))?;
    let stderr = child.stderr.take().ok_or_else(|| format!("Could not read {program} error output"))?;
    let (sender, receiver) = mpsc::channel::<String>();
    for stream in [stdout, stderr] {
        let sender = sender.clone();
        thread::spawn(move || {
            for line in BufReader::new(stream).lines() {
                if let Ok(line) = line { let _ = sender.send(format!("{line}\n")); }
            }
        });
    }
    drop(sender);
    let mut output = String::new();
    for line in receiver {
        let line = redact(&line, secrets);
        output.push_str(&line);
        emit_activity(app, &ActivityRecord {
            id: id.clone(), label: label.to_string(), command: command.clone(), timestamp: unix_timestamp(),
            output: line, exit_code: None, running: true,
        });
    }
    let status = child.wait().map_err(|error| format!("Could not wait for {program}: {error}"))?;
    let completed = ActivityRecord {
        id, label: label.to_string(), command, timestamp: unix_timestamp(), output: output.clone(),
        exit_code: status.code(), running: false,
    };
    emit_activity(app, &completed);
    append_activity(app, &completed);
    Ok(Output { status, stdout: output.into_bytes(), stderr: Vec::new() })
}

#[tauri::command]
fn list_activity(app: AppHandle) -> Result<Vec<ActivityRecord>, String> {
    let path = activity_path(&app)?;
    match fs::read_to_string(path) {
        Ok(content) => serde_json::from_str(&content).map_err(|error| format!("Could not read activity history: {error}")),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(Vec::new()),
        Err(error) => Err(format!("Could not read activity history: {error}")),
    }
}

fn program_path(program: &str) -> PathBuf {
    if program.contains('/') || program.contains('\\') {
        return PathBuf::from(program);
    }
    if let Some(path) = env::var_os("PATH") {
        for directory in env::split_paths(&path) {
            let candidate = directory.join(program);
            if candidate.is_file() {
                return candidate;
            }
        }
    }
    #[cfg(target_os = "macos")]
    for directory in ["/opt/homebrew/bin", "/usr/local/bin", "/opt/podman/bin"] {
        let candidate = Path::new(directory).join(program);
        if candidate.is_file() {
            return candidate;
        }
    }
    #[cfg(target_os = "windows")]
    for directory in [
        env::var_os("ProgramFiles").map(|value| PathBuf::from(value).join("RedHat/Podman")),
        env::var_os("LOCALAPPDATA").map(|value| PathBuf::from(value).join("Programs/Podman")),
    ]
    .into_iter()
    .flatten()
    {
        let candidate = directory.join(program);
        if candidate.is_file() {
            return candidate;
        }
    }
    PathBuf::from(program)
}

#[cfg(target_os = "windows")]
fn process_command(program: PathBuf) -> Command {
    let mut command = Command::new(program);
    use std::os::windows::process::CommandExt;
    // Podman and Compose are console programs. Their output is captured by
    // the launcher, so creating a transient PowerShell/console window only
    // distracts from the native launcher workflow.
    command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    command
}

#[cfg(not(target_os = "windows"))]
fn process_command(program: PathBuf) -> Command {
    Command::new(program)
}

fn run_output(program: &str, args: &[&str]) -> Result<Output, String> {
    process_command(program_path(program))
        .args(args)
        .output()
        .map_err(|error| format!("Could not run {program}: {error}"))
}

fn run_checked(program: &str, args: &[&str]) -> Result<String, String> {
    let output = run_output(program, args)?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        Err(format!("{program} failed: {}", output_text(&output)))
    }
}

fn run_with_stdin(program: &str, args: &[&str], value: &str) -> Result<(), String> {
    let mut child = process_command(program_path(program))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("Could not run {program}: {error}"))?;
    child
        .stdin
        .take()
        .ok_or_else(|| format!("Could not open {program} input"))?
        .write_all(value.as_bytes())
        .map_err(|error| format!("Could not provide credential to {program}: {error}"))?;
    let output = child
        .wait_with_output()
        .map_err(|error| format!("Could not wait for {program}: {error}"))?;
    if output.status.success() {
        Ok(())
    } else {
        Err(format!("{program} failed: {}", output_text(&output)))
    }
}

fn compose_provider() -> Option<ComposeProvider> {
    if run_output("podman-compose", &["--version"]).is_ok_and(|output| output.status.success()) {
        return Some(ComposeProvider::PodmanCompose);
    }
    if run_output("podman", &["compose", "version"]).is_ok_and(|output| output.status.success()) {
        return Some(ComposeProvider::PodmanPlugin);
    }
    None
}

fn podman_status() -> PodmanStatus {
    let version_output = match run_output("podman", &["--version"]) {
        Ok(output) if output.status.success() => output,
        Ok(output) => {
            return PodmanStatus {
                installed: false,
                version: None,
                major_version: None,
                engine_ready: false,
                compose_ready: false,
                compose_provider: None,
                message: output_text(&output),
            }
        }
        Err(error) => {
            return PodmanStatus {
                installed: false,
                version: None,
                major_version: None,
                engine_ready: false,
                compose_ready: false,
                compose_provider: None,
                message: error,
            }
        }
    };
    let version = String::from_utf8_lossy(&version_output.stdout)
        .trim()
        .to_string();
    let major_version = version
        .split_whitespace()
        .find_map(|part| part.split('.').next()?.parse::<u32>().ok());
    let raw_engine_ready = run_output("podman", &["info", "--format", "json"])
        .is_ok_and(|output| output.status.success());
    let provider = compose_provider();
    let version_supported = major_version.is_some_and(|major| major >= 5);
    let message = if !version_supported {
        "OSII requires Podman 5 or newer.".to_string()
    } else if !raw_engine_ready {
        "Podman is installed, but its container engine is not running.".to_string()
    } else if provider.is_none() {
        "Podman is ready, but no Compose provider was found.".to_string()
    } else {
        "Podman and Compose are ready.".to_string()
    };
    PodmanStatus {
        installed: true,
        version: Some(version),
        major_version,
        engine_ready: raw_engine_ready && version_supported,
        compose_ready: provider.is_some(),
        compose_provider: provider.map(|item| match item {
            ComposeProvider::PodmanCompose => "podman-compose".to_string(),
            ComposeProvider::PodmanPlugin => "podman compose".to_string(),
        }),
        message,
    }
}

#[tauri::command]
fn check_podman() -> PodmanStatus {
    podman_status()
}

#[tauri::command]
fn prepare_podman_machine() -> Result<PodmanStatus, String> {
    let current = podman_status();
    if !current.installed {
        return Err("Install Podman Desktop or Podman 5 before continuing.".to_string());
    }
    if current.major_version.is_none_or(|major| major < 5) {
        return Err("Upgrade to Podman 5 or newer before continuing.".to_string());
    }
    if current.engine_ready {
        return Ok(current);
    }
    if cfg!(target_os = "linux") {
        return Err(
            "Start the Podman service for your Linux account, then check again.".to_string(),
        );
    }

    let machines = run_checked("podman", &["machine", "list", "--format", "json"])?;
    let rows: Value = serde_json::from_str(&machines)
        .map_err(|error| format!("Podman returned an invalid machine list: {error}"))?;
    if rows.as_array().is_none_or(|items| items.is_empty()) {
        run_checked("podman", &["machine", "init"])?;
    }
    let started = run_output("podman", &["machine", "start"])?;
    if !started.status.success() {
        let message = output_text(&started).to_lowercase();
        if !message.contains("already running") {
            return Err(format!(
                "Could not start the Podman machine: {}",
                output_text(&started)
            ));
        }
    }
    let status = podman_status();
    if status.engine_ready {
        Ok(status)
    } else {
        Err("Podman reported that the machine started, but the engine is not ready yet. Wait a moment and check again.".to_string())
    }
}

fn validate_registry(registry: &str) -> Result<String, String> {
    let value = registry.trim().to_lowercase();
    if value.is_empty()
        || value.contains('/')
        || !value
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || ".:-".contains(character))
    {
        return Err("Enter a registry hostname such as quay.corp.example.".to_string());
    }
    Ok(value)
}

#[tauri::command]
fn registry_status(registry: String) -> Result<RegistryStatus, String> {
    let registry = validate_registry(&registry)?;
    let output = run_output("podman", &["login", "--get-login", &registry])?;
    let username = output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).trim().to_string());
    Ok(RegistryStatus {
        registry,
        logged_in: username.as_ref().is_some_and(|value| !value.is_empty()),
        username: username.filter(|value| !value.is_empty()),
    })
}

#[tauri::command]
fn login_registry(
    registry: String,
    username: String,
    password: String,
) -> Result<RegistryStatus, String> {
    let registry = validate_registry(&registry)?;
    let username = username.trim();
    if username.is_empty() || username.contains(['\n', '\r']) {
        return Err("Enter the Quay username or robot-account name.".to_string());
    }
    if password.is_empty() || password.contains(['\n', '\r']) {
        return Err("Enter the Quay password or robot token.".to_string());
    }
    run_with_stdin(
        "podman",
        &[
            "login",
            &registry,
            "--username",
            username,
            "--password-stdin",
        ],
        &password,
    )?;
    registry_status(registry)
}

fn launcher_data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let path = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Could not locate launcher data: {error}"))?;
    fs::create_dir_all(&path)
        .map_err(|error| format!("Could not create launcher data directory: {error}"))?;
    Ok(path)
}

fn profiles_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(launcher_data_dir(app)?.join("profiles.json"))
}

fn read_profiles(app: &AppHandle) -> Result<Vec<Profile>, String> {
    let path = profiles_path(app)?;
    match fs::read_to_string(path) {
        Ok(content) => serde_json::from_str(&content)
            .map_err(|error| format!("Could not read saved library profiles: {error}")),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(Vec::new()),
        Err(error) => Err(format!("Could not read saved library profiles: {error}")),
    }
}

fn write_profiles(app: &AppHandle, profiles: &[Profile]) -> Result<(), String> {
    let path = profiles_path(app)?;
    let temporary = path.with_extension("json.tmp");
    let content = serde_json::to_string_pretty(profiles)
        .map_err(|error| format!("Could not serialize library profiles: {error}"))?;
    fs::write(&temporary, format!("{content}\n"))
        .map_err(|error| format!("Could not save library profiles: {error}"))?;
    if cfg!(target_os = "windows") && path.exists() {
        fs::remove_file(&path)
            .map_err(|error| format!("Could not replace library profiles: {error}"))?;
    }
    fs::rename(&temporary, &path)
        .map_err(|error| format!("Could not finish saving library profiles: {error}"))
}

fn same_profile_settings(left: &Profile, right: &Profile) -> bool {
    left.name == right.name
        && left.source_dir == right.source_dir
        && left.image_prefix == right.image_prefix
        && left.image_tag == right.image_tag
        && left.readable_wiki == right.readable_wiki
        && left.concept_entity_wiki == right.concept_entity_wiki
        && left.tesseract_open_cv == right.tesseract_open_cv
}

fn deduplicate_profiles(profiles: Vec<Profile>) -> Vec<Profile> {
    let mut unique = Vec::with_capacity(profiles.len());
    for profile in profiles {
        if !unique
            .iter()
            .any(|existing| same_profile_settings(existing, &profile))
        {
            unique.push(profile);
        }
    }
    unique
}

fn validate_image_part(value: &str, label: &str, allow_slash: bool) -> Result<String, String> {
    let value = value.trim();
    let allowed = value.chars().all(|character| {
        character.is_ascii_alphanumeric()
            || "._:@-".contains(character)
            || (allow_slash && character == '/')
    });
    if value.is_empty() || !allowed {
        Err(format!("The {label} contains unsupported characters."))
    } else {
        Ok(value.to_string())
    }
}

fn is_network_source_path(source_dir: &str) -> bool {
    let source = source_dir.trim();
    source.starts_with("\\\\") || source.starts_with("//")
}

fn source_connection_help(source_dir: &str) -> &'static str {
    if is_network_source_path(source_dir) {
        " OSII does not mount shares or store share credentials. Open the share in Windows Explorer or Finder first; on Windows, a mapped drive can be more reliable for Podman."
    } else {
        " For a shared drive, connect it in Windows Explorer or Finder first, then use its mounted folder path. OSII does not mount shares or store share credentials."
    }
}

#[cfg(any(target_os = "windows", test))]
fn remove_windows_extended_path_prefix(value: &str) -> String {
    if let Some(unc_path) = value.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{unc_path}")
    } else if let Some(path) = value.strip_prefix(r"\\?\") {
        path.to_string()
    } else {
        value.to_string()
    }
}

fn canonical_source(source_dir: &str) -> Result<PathBuf, String> {
    let value = source_dir.trim();
    if value.is_empty() {
        return Err("Choose a document folder first.".to_string());
    }
    let source = Path::new(value);
    let canonical = source.canonicalize().map_err(|error| {
        format!(
            "The selected source folder is not accessible: {error}.{}",
            source_connection_help(value)
        )
    })?;
    if !canonical.is_dir() {
        return Err("The selected source path is not a folder.".to_string());
    }
    fs::read_dir(&canonical).map_err(|error| {
        format!(
            "The selected source folder cannot be read: {error}.{}",
            source_connection_help(value)
        )
    })?;
    Ok(canonical)
}

fn profile_source_path(source_dir: &str, canonical: &Path) -> Result<String, String> {
    #[cfg(target_os = "windows")]
    {
        // std::fs::canonicalize adds a `\\?\` extended-path prefix on Windows.
        // It is useful for validation, but Podman Compose cannot reliably bind
        // mount that form. Retain a normal absolute drive or UNC path instead.
        let requested = Path::new(source_dir.trim());
        let absolute = if requested.is_absolute() {
            requested.to_path_buf()
        } else {
            env::current_dir()
                .map_err(|error| format!("Could not resolve the source folder: {error}"))?
                .join(requested)
        };
        Ok(remove_windows_extended_path_prefix(
            &absolute.to_string_lossy(),
        ))
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = source_dir;
        Ok(canonical.to_string_lossy().to_string())
    }
}

#[tauri::command]
fn list_profiles(app: AppHandle) -> Result<Vec<Profile>, String> {
    let profiles = read_profiles(&app)?;
    let original_count = profiles.len();
    let profiles = deduplicate_profiles(profiles);
    if profiles.len() != original_count {
        write_profiles(&app, &profiles)?;
    }
    Ok(profiles)
}

#[tauri::command]
fn save_profile(
    app: AppHandle,
    draft: ProfileDraft,
    profile_id: Option<String>,
) -> Result<Profile, String> {
    save_profile_inner(&app, draft, profile_id)
}

fn save_profile_inner(
    app: &AppHandle,
    draft: ProfileDraft,
    profile_id: Option<String>,
) -> Result<Profile, String> {
    let name = draft.name.trim();
    if name.is_empty() {
        return Err("Give this library a name.".to_string());
    }
    let source = canonical_source(&draft.source_dir)?;
    let source_dir = profile_source_path(&draft.source_dir, &source)?;
    let image_prefix = validate_image_part(&draft.image_prefix, "image prefix", true)?;
    let image_tag = validate_image_part(&draft.image_tag, "image tag", false)?;
    if image_tag.eq_ignore_ascii_case("latest") {
        return Err("Choose a pinned release tag instead of latest.".to_string());
    }
    let mut profiles = deduplicate_profiles(read_profiles(app)?);
    let id = match profile_id {
        Some(id) => id,
        None => profiles
            .iter()
            .find(|profile| profile.name == name && profile.source_dir == source_dir)
            .map(|profile| profile.id.clone())
            .unwrap_or_else(|| uuid::Uuid::new_v4().to_string()),
    };
    validate_profile_id(&id)?;
    let profile = Profile {
        id: id.clone(),
        name: name.to_string(),
        source_dir,
        image_prefix,
        image_tag,
        readable_wiki: draft.readable_wiki,
        concept_entity_wiki: draft.concept_entity_wiki,
        tesseract_open_cv: draft.tesseract_open_cv,
    };
    let previous = profiles.iter().find(|item| item.id == id).cloned();
    if previous.as_ref().is_some_and(|old| {
        old.readable_wiki != profile.readable_wiki
            || old.concept_entity_wiki != profile.concept_entity_wiki
            || old.tesseract_open_cv != profile.tesseract_open_cv
    }) {
        sync_selected_tools(app, &profile)?;
    }
    profiles.retain(|item| item.id != id && !same_profile_settings(item, &profile));
    profiles.insert(0, profile.clone());
    write_profiles(app, &profiles)?;
    fs::create_dir_all(profile_data_dir(app, &id)?)
        .map_err(|error| format!("Could not create the library state directory: {error}"))?;
    Ok(profile)
}

fn bundled_demo_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let development = Path::new(env!("CARGO_MANIFEST_DIR")).join("../demo-assets");
    if development.is_dir() {
        return development
            .canonicalize()
            .map_err(|error| format!("Could not locate the bundled demo files: {error}"));
    }
    let packaged = app
        .path()
        .resolve("demo", BaseDirectory::Resource)
        .map_err(|error| format!("Could not locate the packaged demo files: {error}"))?;
    if packaged.is_dir() {
        Ok(packaged)
    } else {
        Err("The built-in demo files are missing. Reinstall the OSII Launcher.".to_string())
    }
}

fn copy_missing_demo_files(source: &Path, destination: &Path) -> Result<(), String> {
    for entry in fs::read_dir(source)
        .map_err(|error| format!("Could not read a bundled demo folder: {error}"))?
    {
        let entry =
            entry.map_err(|error| format!("Could not read a bundled demo file: {error}"))?;
        let source_path = entry.path();
        let destination_path = destination.join(entry.file_name());
        let file_type = entry
            .file_type()
            .map_err(|error| format!("Could not inspect a bundled demo file: {error}"))?;
        if file_type.is_symlink() {
            return Err("The built-in demo contains an unsupported symbolic link.".to_string());
        }
        if file_type.is_dir() {
            fs::create_dir_all(&destination_path)
                .map_err(|error| format!("Could not create the demo library folder: {error}"))?;
            copy_missing_demo_files(&source_path, &destination_path)?;
        } else if file_type.is_file() && !destination_path.exists() {
            fs::copy(&source_path, &destination_path)
                .map_err(|error| format!("Could not install a demo file: {error}"))?;
        } else if !file_type.is_file() {
            return Err("The built-in demo contains an unsupported file type.".to_string());
        }
    }
    Ok(())
}

#[tauri::command]
fn prepare_demo_profile(
    app: AppHandle,
    image_prefix: String,
    image_tag: String,
) -> Result<Profile, String> {
    let source_dir = launcher_data_dir(&app)?.join("demo").join("source");
    fs::create_dir_all(&source_dir)
        .map_err(|error| format!("Could not create the demo library folder: {error}"))?;
    copy_missing_demo_files(&bundled_demo_dir(&app)?, &source_dir)?;
    save_profile_inner(
        &app,
        ProfileDraft {
            name: DEMO_PROFILE_NAME.to_string(),
            source_dir: source_dir.to_string_lossy().to_string(),
            image_prefix,
            image_tag,
            readable_wiki: false,
            concept_entity_wiki: false,
            tesseract_open_cv: false,
        },
        Some(DEMO_PROFILE_ID.to_string()),
    )
}

#[tauri::command]
fn delete_profile(app: AppHandle, profile_id: String) -> Result<Vec<Profile>, String> {
    validate_profile_id(&profile_id)?;
    if active_profile(&app)?.as_deref() == Some(profile_id.as_str()) {
        return Err("Stop this library before removing its saved profile.".to_string());
    }
    let mut profiles = read_profiles(&app)?;
    let original_count = profiles.len();
    profiles.retain(|profile| profile.id != profile_id);
    if profiles.len() == original_count {
        return Err("The selected library profile no longer exists.".to_string());
    }
    profiles = deduplicate_profiles(profiles);
    write_profiles(&app, &profiles)?;
    Ok(profiles)
}

#[tauri::command]
fn validate_source(source_dir: String, probe_image: String) -> Result<SourceCheck, String> {
    let source = canonical_source(&source_dir)?;
    let mount_source = profile_source_path(&source_dir, &source)?;
    let image = validate_image_part(&probe_image, "probe image", true)?;
    let mount = format!("{mount_source}:/source:ro");
    let output = run_output(
        "podman",
        &[
            "run",
            "--rm",
            "--pull=never",
            "--volume",
            &mount,
            &image,
            "/bin/sh",
            "-c",
            "test -r /source && find /source -mindepth 1 -maxdepth 1 -print -quit >/dev/null",
        ],
    )?;
    let visible = output.status.success();
    Ok(SourceCheck {
        ok: visible,
        canonical_path: mount_source,
        container_visible: visible,
        message: if visible {
            "The folder is readable from an OSII container and will be mounted read-only. OSII stores its catalog and derived artifacts separately on this workstation.".to_string()
        } else {
            format!(
                "Podman could not read this folder with {}. If it is a shared drive, first confirm it opens in Explorer or Finder, then make the mounted folder available to Podman Desktop or the Podman machine. OSII will not mount the share or write to it. Details: {}",
                image,
                output_text(&output)
            )
        },
    })
}

fn validate_profile_id(profile_id: &str) -> Result<(), String> {
    if profile_id.is_empty()
        || profile_id.len() > 64
        || !profile_id
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '-')
    {
        Err("Invalid library profile identifier.".to_string())
    } else {
        Ok(())
    }
}

fn profile_data_dir(app: &AppHandle, profile_id: &str) -> Result<PathBuf, String> {
    validate_profile_id(profile_id)?;
    Ok(launcher_data_dir(app)?
        .join("profiles")
        .join(profile_id)
        .join("data"))
}

fn profile_config_dir(app: &AppHandle, profile_id: &str) -> Result<PathBuf, String> {
    validate_profile_id(profile_id)?;
    Ok(launcher_data_dir(app)?
        .join("profiles")
        .join(profile_id)
        .join("deployment"))
}

fn sync_selected_tools(app: &AppHandle, profile: &Profile) -> Result<(), String> {
    let path = profile_config_dir(app, &profile.id)?.join("tools.toml");
    let content = match fs::read_to_string(&path) {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(format!("Could not read selected tools: {error}")),
    };
    let mut document: toml::Value = toml::from_str(&content)
        .map_err(|error| format!("Fix tools.toml before changing tool selection: {error}"))?;
    let tools = document.as_table_mut().ok_or("tools.toml must be a table")?
        .entry("tools").or_insert_with(|| toml::Value::Table(toml::Table::new()))
        .as_table_mut().ok_or("[tools] must be a table")?;
    for (id, selected, endpoint, definition) in [
        ("readable-llm-wiki", profile.readable_wiki, "http://readable-wiki-enricher:8099", "enabled = true\nprocessor_id = 'toolbox.readable-wiki'\ndisplay_name = 'Readable LLM Wiki'\nkind = 'enricher'\nruntime = { mode = 'external', endpoint = 'http://readable-wiki-enricher:8099' }\nmodel_access = { mode = 'gateway', bindings = { chat = 'base' } }\n"),
        ("concept-entity-llm-wiki", profile.concept_entity_wiki, "http://concept-entity-wiki-enricher:8100", "enabled = true\nprocessor_id = 'toolbox.concept-entity-wiki'\ndisplay_name = 'Concept and Entity LLM Wiki'\nkind = 'enricher'\nruntime = { mode = 'external', endpoint = 'http://concept-entity-wiki-enricher:8100' }\nmodel_access = { mode = 'gateway', bindings = { chat = 'base' } }\n"),
        ("tesseract-opencv", profile.tesseract_open_cv, "http://tesseract-opencv:8080", "enabled = true\nprocessor_id = 'toolbox.tesseract-opencv'\naliases = ['toolchest.tesseract-opencv']\ndisplay_name = 'Tesseract OCR with OpenCV regions'\nkind = 'extractor'\nruntime = { mode = 'external', endpoint = 'http://tesseract-opencv:8080' }\nmodel_access = { mode = 'none' }\n"),
    ] {
        if let Some(existing) = tools.get_mut(id) {
            if existing.get("runtime").and_then(|runtime| runtime.get("endpoint")).and_then(toml::Value::as_str) == Some(endpoint) {
                existing.as_table_mut().ok_or("Tool entry must be a table")?
                    .insert("enabled".into(), toml::Value::Boolean(selected));
            }
        } else if selected {
            tools.insert(id.into(), toml::from_str(definition).map_err(|error| format!("Could not configure {id}: {error}"))?);
        }
    }
    fs::write(&path, toml::to_string_pretty(&document).map_err(|error| format!("Could not serialize tools: {error}"))?)
        .map_err(|error| format!("Could not update selected tools: {error}"))
}

fn allowed_fields(value: &toml::Value, names: &[&str]) -> toml::Table {
    let mut output = toml::Table::new();
    if let Some(table) = value.as_table() {
        for name in names {
            if let Some(item) = table.get(*name) {
                output.insert((*name).to_string(), item.clone());
            }
        }
    }
    output
}

fn safe_model_config(value: &toml::Value) -> toml::Value {
    let mut output = toml::Table::new();
    output.insert("version".into(), toml::Value::Integer(1));
    if let Some(defaults) = value.get("defaults") {
        output.insert("defaults".into(), toml::Value::Table(allowed_fields(defaults, &["chat", "synthesis", "embedding"])));
    }
    let mut models = toml::Table::new();
    if let Some(entries) = value.get("models").and_then(toml::Value::as_table) {
        for (name, model) in entries {
            let mut fields = allowed_fields(model, &[
                "type", "base_url", "api_key_env", "model", "capabilities", "enabled", "priority",
            ]);
            if fields.get("api_key_env").and_then(toml::Value::as_str).is_some_and(|name| {
                name.is_empty() || !name.chars().all(|character| character.is_ascii_uppercase() || character.is_ascii_digit() || character == '_')
            }) {
                fields.remove("api_key_env");
            }
            models.insert(name.clone(), toml::Value::Table(fields));
        }
    }
    output.insert("models".into(), toml::Value::Table(models));
    toml::Value::Table(output)
}

fn snapshot_urls_are_safe(models: &toml::Value, tools: &toml::Value) -> bool {
    let safe_url = |value: &str| {
        if value.is_empty() {
            return true;
        }
        if value.contains('?') || value.contains('#') {
            return false;
        }
        let authority = value.split_once("://").map(|(_, rest)| rest.split('/').next().unwrap_or(""));
        authority.is_some_and(|part| !part.contains('@'))
    };
    let model_urls_safe = models.get("models").and_then(toml::Value::as_table).is_none_or(|entries| {
        entries.values().all(|entry| entry.get("base_url").and_then(toml::Value::as_str).is_none_or(&safe_url))
    });
    let tool_urls_safe = tools.get("tools").and_then(toml::Value::as_table).is_none_or(|entries| {
        entries.values().all(|entry| entry.get("runtime").and_then(|runtime| runtime.get("endpoint")).and_then(toml::Value::as_str).is_none_or(&safe_url))
    });
    model_urls_safe && tool_urls_safe
}

fn safe_tool_config(value: &toml::Value) -> toml::Value {
    let mut output = toml::Table::new();
    output.insert("version".into(), toml::Value::Integer(1));
    let mut tools = toml::Table::new();
    if let Some(entries) = value.get("tools").and_then(toml::Value::as_table) {
        for (name, tool) in entries {
            let mut item = allowed_fields(tool, &["enabled", "processor_id", "display_name", "kind", "aliases"]);
            if let Some(runtime) = tool.get("runtime") {
                item.insert("runtime".into(), toml::Value::Table(allowed_fields(runtime, &["mode", "endpoint", "image"])));
            }
            if let Some(access) = tool.get("model_access") {
                let mut selected = allowed_fields(access, &["mode"]);
                if let Some(bindings) = access.get("bindings") {
                    selected.insert("bindings".into(), toml::Value::Table(allowed_fields(bindings, &["chat", "synthesis", "embedding"])));
                }
                item.insert("model_access".into(), toml::Value::Table(selected));
            }
            tools.insert(name.clone(), toml::Value::Table(item));
        }
    }
    output.insert("tools".into(), toml::Value::Table(tools));
    let mut routes = toml::Table::new();
    for kind in ["extractor", "object_synthesis", "folder_synthesis"] {
        if let Some(items) = value.get("routes").and_then(|entry| entry.get(kind)).and_then(toml::Value::as_array) {
            routes.insert(kind.into(), toml::Value::Array(items.iter().map(|item| {
                toml::Value::Table(allowed_fields(item, &["name", "extractor", "fallbacks", "extensions", "synthesizer", "path_patterns"]))
            }).collect()));
        }
    }
    if !routes.is_empty() {
        output.insert("routes".into(), toml::Value::Table(routes));
    }
    toml::Value::Table(output)
}

#[tauri::command]
fn export_profile(app: AppHandle, profile_id: String, destination: String) -> Result<(), String> {
    let profile = find_profile(&app, &profile_id)?;
    // A newly saved profile has not generated deployment files yet.
    deployment_files(&app, &profile)?;
    let config_dir = profile_config_dir(&app, &profile_id)?;
    let read_config = |name: &str| -> Result<toml::Value, String> {
        let text = fs::read_to_string(config_dir.join(name)).map_err(|error| format!(
            "Could not read {name}; start this profile once to migrate older YAML: {error}"
        ))?;
        toml::from_str(&text).map_err(|error| format!("Invalid {name}: {error}"))
    };
    let raw_models = read_config("models.toml")?;
    let raw_tools = read_config("tools.toml")?;
    if !snapshot_urls_are_safe(&raw_models, &raw_tools) {
        return Err("Remove credentials or query parameters from model and processor URLs before exporting.".into());
    }
    let snapshot = ProfileSnapshot {
        version: 1,
        profile: ProfileDraft {
            name: profile.name, source_dir: profile.source_dir,
            image_prefix: profile.image_prefix, image_tag: profile.image_tag,
            readable_wiki: profile.readable_wiki, concept_entity_wiki: profile.concept_entity_wiki,
            tesseract_open_cv: profile.tesseract_open_cv,
        },
        model_config: safe_model_config(&raw_models),
        tool_config: safe_tool_config(&raw_tools),
    };
    let content = toml::to_string_pretty(&snapshot)
        .map_err(|error| format!("Could not serialize profile: {error}"))?;
    fs::write(destination, content).map_err(|error| format!("Could not export profile: {error}"))
}

#[tauri::command]
fn import_profile(app: AppHandle, source: String) -> Result<Profile, String> {
    let content = fs::read_to_string(source).map_err(|error| format!("Could not read profile: {error}"))?;
    if content.len() > 1024 * 1024 {
        return Err("Profile export exceeds the 1 MiB limit.".into());
    }
    let snapshot: ProfileSnapshot = toml::from_str(&content)
        .map_err(|error| format!("Invalid profile TOML: {error}"))?;
    if snapshot.version != 1 {
        return Err(format!("Unsupported profile version: {}", snapshot.version));
    }
    if !snapshot_urls_are_safe(&snapshot.model_config, &snapshot.tool_config) {
        return Err("Imported profile URLs must not contain credentials or query parameters.".into());
    }
    let draft = snapshot.profile;
    if draft.name.trim().is_empty() || draft.source_dir.trim().is_empty() {
        return Err("Profile needs a name and original source path.".into());
    }
    let image_prefix = validate_image_part(&draft.image_prefix, "image prefix", true)?;
    let image_tag = validate_image_part(&draft.image_tag, "image tag", false)?;
    let id = uuid::Uuid::new_v4().to_string();
    let profile = Profile {
        id: id.clone(), name: draft.name, source_dir: draft.source_dir,
        image_prefix, image_tag, readable_wiki: draft.readable_wiki,
        concept_entity_wiki: draft.concept_entity_wiki, tesseract_open_cv: draft.tesseract_open_cv,
    };
    let config_dir = profile_config_dir(&app, &id)?;
    fs::create_dir_all(&config_dir).map_err(|error| format!("Could not create imported profile: {error}"))?;
    let models = toml::to_string_pretty(&safe_model_config(&snapshot.model_config))
        .map_err(|error| format!("Could not import models: {error}"))?;
    let tools = toml::to_string_pretty(&safe_tool_config(&snapshot.tool_config))
        .map_err(|error| format!("Could not import tools: {error}"))?;
    fs::write(config_dir.join("models.toml"), models).map_err(|error| format!("Could not save models: {error}"))?;
    fs::write(config_dir.join("tools.toml"), tools).map_err(|error| format!("Could not save tools: {error}"))?;
    fs::create_dir_all(profile_data_dir(&app, &id)?).map_err(|error| format!("Could not create library state: {error}"))?;
    let mut profiles = read_profiles(&app)?;
    profiles.insert(0, profile.clone());
    write_profiles(&app, &profiles)?;
    Ok(profile)
}

fn active_profile_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(launcher_data_dir(app)?.join("active-profile"))
}

fn active_profile(app: &AppHandle) -> Result<Option<String>, String> {
    match fs::read_to_string(active_profile_path(app)?) {
        Ok(value) => {
            let value = value.trim().to_string();
            validate_profile_id(&value)?;
            Ok(Some(value))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!(
            "Could not read the active library profile: {error}"
        )),
    }
}

fn set_active_profile(app: &AppHandle, profile_id: Option<&str>) -> Result<(), String> {
    let path = active_profile_path(app)?;
    if let Some(value) = profile_id {
        validate_profile_id(value)?;
        fs::write(path, format!("{value}\n"))
            .map_err(|error| format!("Could not record the active library profile: {error}"))
    } else {
        match fs::remove_file(path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(format!(
                "Could not clear the active library profile: {error}"
            )),
        }
    }
}

fn find_profile(app: &AppHandle, profile_id: &str) -> Result<Profile, String> {
    validate_profile_id(profile_id)?;
    read_profiles(app)?
        .into_iter()
        .find(|profile| profile.id == profile_id)
        .ok_or_else(|| "The selected library profile no longer exists.".to_string())
}

fn compose_file(app: &AppHandle) -> Result<PathBuf, String> {
    let development = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../compose.yaml");
    if development.is_file() {
        return development
            .canonicalize()
            .map_err(|error| format!("Could not locate the development Compose file: {error}"));
    }
    app.path()
        .resolve("deployment/compose.yaml", BaseDirectory::Resource)
        .map_err(|error| format!("Could not locate the packaged Compose file: {error}"))
}

fn project_name(profile_id: &str) -> Result<String, String> {
    validate_profile_id(profile_id)?;
    Ok(format!(
        "osii-{}",
        profile_id.replace('-', "").to_lowercase()
    ))
}

fn compose_command(
    provider: ComposeProvider,
    compose: &Path,
    environment_file: &Path,
    override_file: &Path,
    project: &str,
    profile: &Profile,
    args: &[&str],
) -> Result<Output, String> {
    let (program, arguments) = compose_invocation(
        provider,
        compose,
        environment_file,
        override_file,
        project,
        args,
    );
    let mut command = process_command(program);
    command
        .args(arguments)
        .env("OSII_SOURCE_DIR", &profile.source_dir)
        .env("OSII_IMAGE_PREFIX", &profile.image_prefix)
        .env("OSII_IMAGE_TAG", &profile.image_tag)
        .output()
        .map_err(|error| format!("Could not run the Compose provider: {error}"))
}

fn compose_checked(
    provider: ComposeProvider,
    compose: &Path,
    environment_file: &Path,
    override_file: &Path,
    project: &str,
    profile: &Profile,
    args: &[&str],
) -> Result<String, String> {
    let output = compose_command(
        provider,
        compose,
        environment_file,
        override_file,
        project,
        profile,
        args,
    )?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        Err(format!("Compose failed: {}", output_text(&output)))
    }
}

fn compose_invocation(
    provider: ComposeProvider,
    compose: &Path,
    environment_file: &Path,
    override_file: &Path,
    project: &str,
    args: &[&str],
) -> (PathBuf, Vec<String>) {
    let (program, mut arguments) = match provider {
        ComposeProvider::PodmanCompose => (program_path("podman-compose"), Vec::new()),
        ComposeProvider::PodmanPlugin => (program_path("podman"), vec!["compose".to_string()]),
    };
    arguments.extend([
        "--env-file".to_string(),
        environment_file.to_string_lossy().to_string(),
        "-f".to_string(),
        compose.to_string_lossy().to_string(),
        "-f".to_string(),
        override_file.to_string_lossy().to_string(),
        "-p".to_string(),
        project.to_string(),
    ]);
    arguments.extend(args.iter().map(|value| value.to_string()));
    (program, arguments)
}

fn dotenv_value(value: &str) -> Result<String, String> {
    serde_json::to_string(value)
        .map_err(|error| format!("Could not generate deployment environment: {error}"))
}

fn deployment_environment(profile: &Profile) -> Result<String, String> {
    Ok(format!(
        "OSII_SOURCE_DIR={}\nOSII_IMAGE_PREFIX={}\nOSII_IMAGE_TAG={}\n",
        dotenv_value(&profile.source_dir)?,
        dotenv_value(&profile.image_prefix)?,
        dotenv_value(&profile.image_tag)?,
    ))
}

fn profile_override_document(
    profile: &Profile,
    data_dir: &Path,
    config_dir: &Path,
) -> Result<Value, String> {
    let data_mount = format!("{}:/data", data_dir.to_string_lossy());
    let data_mount_read_only = format!("{}:/data:ro", data_dir.to_string_lossy());
    let config_mount = format!("{}:/config", config_dir.to_string_lossy());
    let config_mount_read_only = format!("{}:/config:ro", config_dir.to_string_lossy());

    let mut shared_environment = serde_json::Map::new();
    shared_environment.insert("OSII_CONFIG_DIR".into(), json!("/config"));
    shared_environment.insert("OSII_ENV_FILE".into(), json!("/config/secrets.env"));
    shared_environment.insert("OSII_ACTIVE_PROFILE".into(), json!("launcher"));
    shared_environment.insert("OSII_MODEL_GATEWAY_PUBLIC_URL".into(), json!("http://model-provider-bridge:8095/v1"));
    shared_environment.insert("OSII_MODEL_GATEWAY_SECRET".into(), json!(format!("launcher-{}", profile.id)));

    let mut services = serde_json::Map::new();
    for (name, mount, config) in [
        ("api", data_mount.as_str(), config_mount.as_str()),
        ("worker", data_mount.as_str(), config_mount_read_only.as_str()),
        ("model-provider-bridge", data_mount_read_only.as_str(), config_mount_read_only.as_str()),
    ] {
        let mut service = serde_json::Map::new();
        service.insert("volumes".into(), json!([mount, config]));
        service.insert(
            "environment".into(),
            Value::Object({
                let mut environment = shared_environment.clone();
                environment.insert(
                    "OSII_ALLOW_LOCAL_CONFIG_WRITES".into(),
                    json!(if name == "api" { "true" } else { "false" }),
                );
                environment
            }),
        );
        services.insert(name.into(), Value::Object(service));
    }

    let mut root = serde_json::Map::new();
    root.insert("services".into(), Value::Object(services));
    Ok(Value::Object(root))
}

fn deployment_files(
    app: &AppHandle,
    profile: &Profile,
) -> Result<DeploymentFiles, String> {
    let config_dir = profile_config_dir(app, &profile.id)?;
    let data_dir = profile_data_dir(app, &profile.id)?;
    fs::create_dir_all(&config_dir)
        .map_err(|error| format!("Could not create deployment configuration: {error}"))?;
    fs::create_dir_all(&data_dir)
        .map_err(|error| format!("Could not create library state: {error}"))?;

    // The former installation-wide files are read once by Core and converted to
    // TOML in this profile. Never replace a profile's existing configuration.
    if !config_dir.join("models.toml").exists()
        && !config_dir.join("tools.toml").exists()
        && !config_dir.join("models.yml").exists()
        && !config_dir.join("tools.yml").exists()
    {
        let application_dir = launcher_data_dir(app)?;
        let previous_dir = if cfg!(target_os = "linux") {
            std::env::var_os("XDG_CONFIG_HOME")
                .map(PathBuf::from)
                .unwrap_or_else(|| {
                    std::env::var_os("HOME")
                        .map(PathBuf::from)
                        .unwrap_or_else(|| application_dir.clone())
                        .join(".config")
                })
                .join("org.osii.launcher")
        } else {
            application_dir.join("config")
        };
        for name in ["models.yml", "tools.yml", "secrets.env"] {
            let old_path = previous_dir.join(name);
            let new_path = config_dir.join(name);
            if old_path.is_file() && !new_path.exists() {
                fs::copy(&old_path, &new_path)
                    .map_err(|error| format!("Could not migrate old {name}: {error}"))?;
            }
        }
    }

    let models_path = config_dir.join("models.toml");
    if !models_path.exists() && !config_dir.join("models.yml").exists() {
        fs::write(
            &models_path,
            "version = 1\n\n[defaults]\nchat = 'base'\nsynthesis = 'base'\nembedding = 'minilm'\n\n[models.base]\ntype = 'ollama-local'\nbase_url = 'http://host.containers.internal:11434'\nmodel = 'llama3.2:1b'\ncapabilities = ['chat', 'synthesis']\n\n[models.minilm]\ntype = 'ollama-local'\nbase_url = 'http://host.containers.internal:11434'\nmodel = 'all-minilm'\ncapabilities = ['embedding']\n",
        ).map_err(|error| format!("Could not create model configuration: {error}"))?;
    }
    let tools_path = config_dir.join("tools.toml");
    if !tools_path.exists() && !config_dir.join("tools.yml").exists() {
        let mut tools = String::from("version = 1\n");
        if profile.readable_wiki {
            tools.push_str("\n[tools.readable-llm-wiki]\nenabled = true\nprocessor_id = 'toolbox.readable-wiki'\ndisplay_name = 'Readable LLM Wiki'\nkind = 'enricher'\nruntime = { mode = 'external', endpoint = 'http://readable-wiki-enricher:8099' }\nmodel_access = { mode = 'gateway', bindings = { chat = 'base' } }\n");
        }
        if profile.concept_entity_wiki {
            tools.push_str("\n[tools.concept-entity-llm-wiki]\nenabled = true\nprocessor_id = 'toolbox.concept-entity-wiki'\ndisplay_name = 'Concept and Entity LLM Wiki'\nkind = 'enricher'\nruntime = { mode = 'external', endpoint = 'http://concept-entity-wiki-enricher:8100' }\nmodel_access = { mode = 'gateway', bindings = { chat = 'base' } }\n");
        }
        if profile.tesseract_open_cv {
            tools.push_str("\n[tools.tesseract-opencv]\nenabled = true\nprocessor_id = 'toolbox.tesseract-opencv'\naliases = ['toolchest.tesseract-opencv']\ndisplay_name = 'Tesseract OCR with OpenCV regions'\nkind = 'extractor'\nruntime = { mode = 'external', endpoint = 'http://tesseract-opencv:8080' }\nmodel_access = { mode = 'none' }\n");
        }
        fs::write(&tools_path, tools)
            .map_err(|error| format!("Could not create tool configuration: {error}"))?;
    }
    let secrets_path = config_dir.join("secrets.env");
    if !secrets_path.exists() {
        fs::write(&secrets_path, "# API keys saved from Workbench Setup appear here.\n")
            .map_err(|error| format!("Could not create secrets configuration: {error}"))?;
    }

    let environment_path = config_dir.join("compose.env");
    let environment = deployment_environment(profile)?;
    fs::write(&environment_path, &environment)
        .map_err(|error| format!("Could not save deployment environment: {error}"))?;

    let override_path = config_dir.join("compose.override.json");
    let compose_override =
        serde_json::to_string_pretty(&profile_override_document(profile, &data_dir, &config_dir)?)
            .map_err(|error| format!("Could not generate deployment configuration: {error}"))?;
    fs::write(&override_path, format!("{compose_override}\n"))
        .map_err(|error| format!("Could not save deployment configuration: {error}"))?;
    Ok(DeploymentFiles {
        environment_path,
        environment,
        override_path,
        compose_override,
    })
}

fn profile_images(profile: &Profile) -> Vec<String> {
    let mut images = vec![
        format!("{}-core:{}", profile.image_prefix, profile.image_tag),
        format!("{}-dashboard:{}", profile.image_prefix, profile.image_tag),
        format!(
            "{}-baseline-processors:{}",
            profile.image_prefix, profile.image_tag
        ),
    ];
    if profile.readable_wiki || profile.concept_entity_wiki {
        images.push(format!("{}-llm-wikis:{}", profile.image_prefix, profile.image_tag));
    }
    if profile.tesseract_open_cv {
        images.push(format!("{}-tesseract-opencv:{}", profile.image_prefix, profile.image_tag));
    }
    images
}

fn image_is_local(image: &str) -> Result<bool, String> {
    let result = run_output("podman", &["image", "exists", image])?;
    match result.status.code() {
        Some(0) => Ok(true),
        Some(1) => Ok(false),
        _ => Err(format!("Could not check local image {image}: {}", output_text(&result))),
    }
}

fn selected_services(profile: &Profile) -> Vec<&'static str> {
    let mut services = BASELINE_SERVICES.to_vec();
    if profile.readable_wiki {
        services.push("readable-wiki-enricher");
    }
    if profile.concept_entity_wiki {
        services.push("concept-entity-wiki-enricher");
    }
    if profile.tesseract_open_cv {
        services.push("tesseract-opencv");
    }
    services
}

fn display_argument(value: &str) -> String {
    if !value.is_empty()
        && value
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || "/\\._:@,=+-".contains(character))
    {
        value.to_string()
    } else {
        serde_json::to_string(value).unwrap_or_else(|_| "<unprintable>".to_string())
    }
}

fn display_command(program: &Path, arguments: &[String]) -> String {
    std::iter::once(program.to_string_lossy().to_string())
        .chain(arguments.iter().cloned())
        .map(|value| display_argument(&value))
        .collect::<Vec<_>>()
        .join(" ")
}

#[tauri::command]
fn deployment_preview(
    app: AppHandle,
    profile_id: String,
) -> Result<DeploymentPreview, String> {
    let profile = find_profile(&app, &profile_id)?;
    let compose = compose_file(&app)?;
    let files = deployment_files(&app, &profile)?;
    let provider =
        compose_provider().ok_or_else(|| "No Compose provider is available.".to_string())?;
    let project = project_name(&profile_id)?;
    let mut commands = Vec::new();
    for image in profile_images(&profile) {
        if !image_is_local(&image)? {
            commands.push(display_command(
                &program_path("podman"),
                &["pull".to_string(), image],
            ));
        }
    }
    let mut start_args = vec!["up", "-d", "--no-build"];
    let selected = selected_services(&profile);
    start_args.extend(selected.iter().copied());
    let (program, arguments) = compose_invocation(
        provider,
        &compose,
        &files.environment_path,
        &files.override_path,
        &project,
        &start_args,
    );
    commands.push(display_command(&program, &arguments));

    Ok(DeploymentPreview {
        environment_path: files.environment_path.to_string_lossy().to_string(),
        environment: files.environment,
        override_path: files.override_path.to_string_lossy().to_string(),
        compose_override: files.compose_override,
        commands,
    })
}

fn http_ready(port: u16, path: &str) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(450)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(650)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(650)));
    let request = format!("GET {path} HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = [0_u8; 64];
    let Ok(count) = stream.read(&mut response) else {
        return false;
    };
    let status = String::from_utf8_lossy(&response[..count]);
    status.starts_with("HTTP/1.0 2") || status.starts_with("HTTP/1.1 2")
}

fn deployment_status_inner(app: &AppHandle) -> Result<DeploymentStatus, String> {
    let Some(profile_id) = active_profile(app)? else {
        return Ok(DeploymentStatus {
            profile_id: None,
            state: "stopped".to_string(),
            dashboard_ready: false,
            api_ready: false,
            message: "OSII is not running.".to_string(),
        });
    };
    let api_ready = http_ready(8511, "/health");
    let dashboard_ready = http_ready(5173, "/");
    let state = if api_ready && dashboard_ready {
        "running"
    } else {
        "degraded"
    };
    Ok(DeploymentStatus {
        profile_id: Some(profile_id),
        state: state.to_string(),
        api_ready,
        dashboard_ready,
        message: if state == "running" {
            "Core and the dashboard are healthy.".to_string()
        } else {
            "OSII is running, but one or more health checks are not ready.".to_string()
        },
    })
}

#[tauri::command]
fn deployment_status(app: AppHandle) -> Result<DeploymentStatus, String> {
    deployment_status_inner(&app)
}

fn stop_profile_inner(app: &AppHandle, profile_id: &str) -> Result<DeploymentStatus, String> {
    let profile = find_profile(app, profile_id)?;
    let provider =
        compose_provider().ok_or_else(|| "No Compose provider is available.".to_string())?;
    let compose = compose_file(app)?;
    let files = deployment_files(app, &profile)?;
    compose_checked(
        provider,
        &compose,
        &files.environment_path,
        &files.override_path,
        &project_name(profile_id)?,
        &profile,
        &["down", "--remove-orphans"],
    )?;
    if active_profile(app)?.as_deref() == Some(profile_id) {
        set_active_profile(app, None)?;
    }
    Ok(DeploymentStatus {
        profile_id: None,
        state: "stopped".to_string(),
        dashboard_ready: false,
        api_ready: false,
        message: "OSII stopped. Library data remains on this workstation.".to_string(),
    })
}

#[tauri::command]
fn stop_profile(app: AppHandle, profile_id: String) -> Result<DeploymentStatus, String> {
    stop_profile_inner(&app, &profile_id)
}

#[tauri::command]
fn start_profile(
    app: AppHandle,
    profile_id: String,
) -> Result<DeploymentStatus, String> {
    let status = podman_status();
    if !status.engine_ready || !status.compose_ready {
        return Err(status.message);
    }
    let profile = find_profile(&app, &profile_id)?;
    canonical_source(&profile.source_dir)?;

    if let Some(current) = active_profile(&app)? {
        if current != profile_id {
            stop_profile_inner(&app, &current)?;
        }
    }

    for image in profile_images(&profile) {
        if !image_is_local(&image)? {
            run_checked("podman", &["pull", &image])?;
        }
    }
    let files = deployment_files(&app, &profile)?;
    let compose = compose_file(&app)?;
    let provider =
        compose_provider().ok_or_else(|| "No Compose provider is available.".to_string())?;
    let mut args = vec!["up", "-d", "--no-build"];
    let selected = selected_services(&profile);
    args.extend(selected.iter().copied());
    if let Err(error) = compose_checked(
        provider,
        &compose,
        &files.environment_path,
        &files.override_path,
        &project_name(&profile_id)?,
        &profile,
        &args,
    ) {
        return Err(error);
    }
    set_active_profile(&app, Some(&profile_id))?;

    let deadline = Instant::now() + Duration::from_secs(90);
    while Instant::now() < deadline {
        let status = deployment_status_inner(&app)?;
        if status.api_ready && status.dashboard_ready {
            return Ok(status);
        }
        std::thread::sleep(Duration::from_secs(1));
    }
    deployment_status_inner(&app)
}

#[tauri::command]
fn profile_logs(app: AppHandle, profile_id: String) -> Result<String, String> {
    let profile = find_profile(&app, &profile_id)?;
    let compose = compose_file(&app)?;
    let files = deployment_files(&app, &profile)?;
    let provider =
        compose_provider().ok_or_else(|| "No Compose provider is available.".to_string())?;
    let output = compose_checked(
        provider,
        &compose,
        &files.environment_path,
        &files.override_path,
        &project_name(&profile_id)?,
        &profile,
        &["logs", "--no-color", "--tail", "250"],
    )?;
    let mut start = output.len().saturating_sub(65_536);
    while !output.is_char_boundary(start) {
        start += 1;
    }
    Ok(output[start..].to_string())
}

#[tauri::command]
fn open_dashboard(app: AppHandle) -> Result<(), String> {
    if !http_ready(5173, "/") {
        return Err("The dashboard is not ready yet.".to_string());
    }
    if let Some(window) = app.get_webview_window("dashboard") {
        window
            .show()
            .and_then(|_| window.set_focus())
            .map_err(|error| format!("Could not show the dashboard: {error}"))?;
        return Ok(());
    }
    let url = "http://127.0.0.1:5173"
        .parse()
        .map_err(|error| format!("Could not prepare the dashboard URL: {error}"))?;
    WebviewWindowBuilder::new(&app, "dashboard", WebviewUrl::External(url))
        .title("OSII")
        .inner_size(1280.0, 820.0)
        .min_inner_size(900.0, 640.0)
        .build()
        .map_err(|error| format!("Could not open the dashboard: {error}"))?;
    Ok(())
}

fn install_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open OSII Launcher", true, None::<&str>)?;
    let dashboard = MenuItem::with_id(app, "dashboard", "Open Dashboard", true, None::<&str>)?;
    let stop = MenuItem::with_id(app, "stop", "Stop OSII", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &dashboard, &stop, &quit])?;
    TrayIconBuilder::new()
        .menu(&menu)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "dashboard" => {
                let _ = open_dashboard(app.clone());
            }
            "stop" => {
                if let Ok(Some(profile_id)) = active_profile(app) {
                    let _ = stop_profile_inner(app, &profile_id);
                }
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            install_tray(app.handle())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            check_podman,
            prepare_podman_machine,
            registry_status,
            login_registry,
            validate_source,
            list_profiles,
            save_profile,
            prepare_demo_profile,
            export_profile,
            import_profile,
            delete_profile,
            start_profile,
            stop_profile,
            deployment_status,
            deployment_preview,
            profile_logs,
            open_dashboard,
        ])
        .run(tauri::generate_context!())
        .expect("error while running OSII Launcher");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_validation_rejects_paths_and_flags() {
        assert!(validate_registry("quay.example.test").is_ok());
        assert!(validate_registry("quay.example.test/team").is_err());
        assert!(validate_registry("--tls-verify=false").is_err());
    }

    #[test]
    fn image_validation_allows_registry_paths_but_not_shell_syntax() {
        assert!(validate_image_part("quay.example.test/team/osii-core:tag", "image", true).is_ok());
        assert!(validate_image_part("image;whoami", "image", true).is_err());
    }

    #[test]
    fn profile_ids_are_safe_for_paths_and_project_names() {
        assert!(validate_profile_id("9a35f814-402d-4d33-8ded-19b12ffccb21").is_ok());
        assert!(validate_profile_id("../../outside").is_err());
    }

    #[test]
    fn built_in_demo_has_a_stable_safe_profile_id() {
        assert_eq!(DEMO_PROFILE_ID, "osii-demo");
        assert!(validate_profile_id(DEMO_PROFILE_ID).is_ok());
    }

    #[test]
    fn demo_copy_installs_missing_files_without_overwriting_existing_ones() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../demo-assets");
        let destination = std::env::temp_dir().join(format!("osii-demo-copy-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&destination).expect("create test destination");
        copy_missing_demo_files(&source, &destination).expect("install packaged demo");
        let purcell = destination.join("example-documents/purcell.pdf");
        assert!(purcell.is_file());
        assert!(destination.join("example-datasets/iris/dataset.json").is_file());
        assert!(destination.join("example-datasets/wine/dataset.json").is_file());

        fs::write(&purcell, b"user keeps this file").expect("edit demo file");
        copy_missing_demo_files(&source, &destination).expect("reinstall packaged demo");
        assert_eq!(fs::read(&purcell).expect("read retained file"), b"user keeps this file");
        fs::remove_dir_all(&destination).expect("remove test destination");
    }

    #[test]
    fn workbench_config_is_mounted_without_provider_secrets() {
        let profile = Profile {
            id: "9a35f814-402d-4d33-8ded-19b12ffccb21".to_string(),
            name: "Test".to_string(),
            source_dir: "/source".to_string(),
            image_prefix: "quay.example.test/team/osii".to_string(),
            image_tag: "2026.09.14".to_string(),
            readable_wiki: true,
            concept_entity_wiki: true,
            tesseract_open_cv: false,
        };
        let document = profile_override_document(
            &profile,
            Path::new("/data"),
            Path::new("/config"),
        ).expect("valid override");

        assert_eq!(
            document.pointer("/services/api/environment/OSII_CONFIG_DIR"),
            Some(&json!("/config"))
        );
        assert!(document.pointer("/secrets").is_none());
        assert_eq!(profile_images(&profile).iter().filter(|image| image.contains("llm-wikis")).count(), 1);
    }

    #[test]
    fn duplicate_profile_settings_are_collapsed() {
        let first = Profile {
            id: "first".to_string(),
            name: "My OSII library".to_string(),
            source_dir: "/source".to_string(),
            image_prefix: "quay.example.test/team/osii".to_string(),
            image_tag: "2026.09.14".to_string(),
            readable_wiki: false,
            concept_entity_wiki: false,
            tesseract_open_cv: false,
        };
        let mut duplicate = first.clone();
        duplicate.id = "second".to_string();

        let profiles = deduplicate_profiles(vec![first.clone(), duplicate]);

        assert_eq!(profiles.len(), 1);
        assert_eq!(profiles[0].id, first.id);
    }

    #[test]
    fn network_source_paths_get_network_specific_guidance() {
        assert!(is_network_source_path(r"\\server\share\documents"));
        assert!(is_network_source_path("//server/share/documents"));
        assert!(!is_network_source_path("/Volumes/documents"));
        assert!(source_connection_help(r"\\server\share").contains("mapped drive"));
    }

    #[test]
    fn removes_windows_extended_prefix_without_changing_normal_paths() {
        assert_eq!(
            remove_windows_extended_path_prefix(r"\\?\UNC\server\share\documents"),
            r"\\server\share\documents"
        );
        assert_eq!(
            remove_windows_extended_path_prefix(r"\\?\C:\documents"),
            r"C:\documents"
        );
        assert_eq!(
            remove_windows_extended_path_prefix("/Volumes/documents"),
            "/Volumes/documents"
        );
    }

    #[test]
    fn profile_snapshot_keeps_exact_paths_but_excludes_secret_fields() {
        let models: toml::Value = toml::from_str(
            "version = 1\n[models.mid]\ntype = 'openai-compatible'\nbase_url = 'https://internal.example/v1'\nmodel = 'model-x'\napi_key_env = 'OPENAI_API_KEY'\napi_key = 'do-not-export'\n[defaults]\nchat = 'mid'\n",
        ).unwrap();
        let tools: toml::Value = toml::from_str(
            "version = 1\n[tools.wiki]\nprocessor_id = 'toolbox.readable-wiki'\nsecret = 'do-not-export'\nruntime = { mode = 'external', endpoint = 'http://internal.example:8099' }\n[processor_settings.wiki]\npassword = 'do-not-export'\n[[routes.extractor]]\nname = 'pdf'\nextractor = 'toolbox.tesseract-opencv'\nextensions = ['.pdf']\n",
        ).unwrap();
        let snapshot = ProfileSnapshot {
            version: 1,
            profile: ProfileDraft {
                name: "Shared drive".into(),
                source_dir: r"\\server\share\experiments".into(),
                image_prefix: "quay.example/team/osii".into(),
                image_tag: "2026.09.16".into(),
                readable_wiki: true,
                concept_entity_wiki: false,
                tesseract_open_cv: true,
            },
            model_config: safe_model_config(&models),
            tool_config: safe_tool_config(&tools),
        };
        let serialized = toml::to_string_pretty(&snapshot).unwrap();
        assert!(!serialized.contains("do-not-export"));
        assert!(!serialized.contains("processor_settings"));
        assert!(serialized.contains("https://internal.example/v1"));
        let imported: ProfileSnapshot = toml::from_str(&serialized).unwrap();
        assert_eq!(imported.profile.source_dir, r"\\server\share\experiments");
        assert_eq!(imported.tool_config["routes"]["extractor"][0]["extractor"].as_str(), Some("toolbox.tesseract-opencv"));
        let unsafe_models: toml::Value = toml::from_str(
            "[models.private]\nbase_url = 'https://user:secret@internal.example/v1'\n",
        ).unwrap();
        assert!(!snapshot_urls_are_safe(&unsafe_models, &tools));
    }
}
