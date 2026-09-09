[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "dev", "demo", "demo-data", "run", "build", "push-release", "down", "logs", "doctor")]
    [string]$Command = "dev",

    [ValidateSet("Podman", "Docker")]
    [string]$Runtime = "Podman",

    [string]$ImagePrefix = "",

    [string]$ImageTag = "latest",

    [string]$BaseImage = "",

    [string]$TesseractBaseImage = "",

    [string]$PythonVersion = "",

    [switch]$InsecureRegistries,

    [switch]$DisableContainerProxies,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$env:UV_PROJECT_ENVIRONMENT = Join-Path $RepositoryRoot "osii-env"
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
if (-not $ImagePrefix) {
    $ImagePrefix = if ($env:OSII_IMAGE_PREFIX) { $env:OSII_IMAGE_PREFIX } else { "localhost/osii" }
}
if (-not $BaseImage) {
    $BaseImage = if ($env:OSII_BASE_IMAGE) { $env:OSII_BASE_IMAGE } else { "registry.access.redhat.com/ubi9/ubi:latest" }
}
if (-not $TesseractBaseImage) {
    $TesseractBaseImage = if ($env:OSII_TESSERACT_BASE_IMAGE) { $env:OSII_TESSERACT_BASE_IMAGE } else { "registry.fedoraproject.org/fedora:latest" }
}
if (-not $PythonVersion) {
    $PythonVersion = if ($env:OSII_PYTHON_VERSION) { $env:OSII_PYTHON_VERSION } else { "3.12" }
}
$env:OSII_IMAGE_PREFIX = $ImagePrefix
$env:OSII_IMAGE_TAG = $ImageTag
$env:OSII_BASE_IMAGE = $BaseImage
$env:OSII_TESSERACT_BASE_IMAGE = $TesseractBaseImage
$env:OSII_PYTHON_VERSION = $PythonVersion

if ($Runtime -eq "Docker") {
    $ComposeExecutable = "docker"
    $ComposePrefix = @("compose")
}
else {
    $ComposeExecutable = "podman-compose"
    $ComposePrefix = @()
}
$env:OSII_COMPOSE_COMMAND = if ($Runtime -eq "Docker") { "docker compose" } else { "podman-compose" }

function Invoke-OsiiCompose {
    param([string[]]$Arguments)
    if (-not (Get-Command $ComposeExecutable -ErrorAction SilentlyContinue)) {
        throw "$ComposeExecutable was not found. Install $Runtime Desktop/CLI, then try again."
    }
    $SecurityArguments = @()
    if ($InsecureRegistries) {
        if ($Runtime -ne "Podman") {
            throw "-InsecureRegistries is supported only with the Podman runtime."
        }
        $SecurityArguments = @(
            "--podman-pull-args=--tls-verify=false",
            "--podman-build-args=--tls-verify=false"
        )
    }
    $ComposeAction = if ($Arguments.Count -gt 0) { $Arguments[0] } else { "" }
    if ($DisableContainerProxies -and $ComposeAction -in @("build", "up")) {
        if ($Runtime -ne "Podman") {
            throw "-DisableContainerProxies is supported only with Podman; Docker cannot guarantee removal of proxy settings inherited from a custom base image."
        }

        $ProxyVariables = @(
            "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "ALL_PROXY",
            "http_proxy", "https_proxy", "ftp_proxy", "all_proxy"
        )
        if ($ComposeAction -eq "build") {
            $BuildOptions = @("--http-proxy=false")
            foreach ($Name in $ProxyVariables) {
                $BuildOptions += @("--env", "$Name=", "--unsetenv", $Name)
            }
            $SecurityArguments += "--podman-build-args=$($BuildOptions -join ' ')"
        }
        elseif ($ComposeAction -eq "up") {
            $RunOptions = @("--http-proxy=false")
            foreach ($Name in $ProxyVariables) {
                $RunOptions += @("--env", "$Name=")
            }
            $SecurityArguments += "--podman-run-args=$($RunOptions -join ' ')"
        }
    }
    & $ComposeExecutable @ComposePrefix @SecurityArguments @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Compose command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-OsiiDevLauncher {
    param([string[]]$Arguments = @())

    $UvExecutable = Get-Command "uv" -ErrorAction SilentlyContinue
    if (-not $UvExecutable) {
        throw "uv was not found. Starting OSII from source requires uv and Node.js/npm."
    }
    if (-not (Get-Command "npm" -ErrorAction SilentlyContinue)) {
        throw "npm was not found. Starting OSII from source requires Node.js/npm."
    }

    $LauncherArguments = @($Arguments)
    if ($DryRun) {
        $LauncherArguments += "--dry-run"
    }
    & $UvExecutable.Source run --no-project --python $PythonVersion python scripts/dev_stack.py @LauncherArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Bare-metal development stack exited with code $LASTEXITCODE. Review the first [dev] service error above for the cause."
    }
}

function Import-OsiiExampleData {
    $UvExecutable = Get-Command "uv" -ErrorAction SilentlyContinue
    if (-not $UvExecutable) {
        throw "uv was not found. Importing the example datasets requires uv."
    }
    & $UvExecutable.Source run --no-project --python $PythonVersion --with "scikit-learn>=1.5,<2" python scripts/import_example_data.py
    if ($LASTEXITCODE -ne 0) {
        throw "Example data import exited with code $LASTEXITCODE."
    }
}

function Show-OsiiHelp {
    Write-Host "OSII startup commands"
    Write-Host "  .\scripts\osii.ps1 demo       Install the example files and start OSII"
    Write-Host "  .\scripts\osii.ps1 dev        Start OSII with files already in osii-data\source"
    Write-Host "  .\scripts\osii.ps1 run        Start previously built container images"
    Write-Host "  .\scripts\osii.ps1 down       Stop the container deployment"
    Write-Host "  .\scripts\osii.ps1 doctor     Report disk usage; never deletes files"
    Write-Host ""
    Write-Host "Normal use needs only 'demo' or 'dev'. Optional AI and OCR services are"
    Write-Host "connected or started from the Setup page after launch."
    Write-Host "For direct-network Podman containers, add -DisableContainerProxies."
}

Push-Location $RepositoryRoot
try {
    switch ($Command) {
        "help" {
            Show-OsiiHelp
        }
        "dev" {
            Invoke-OsiiDevLauncher
        }
        "demo" {
            Import-OsiiExampleData
            Invoke-OsiiDevLauncher
        }
        "demo-data" {
            Import-OsiiExampleData
        }
        "run" {
            Invoke-OsiiCompose @("up", "--no-build", "--pull", "missing", "tesseract", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "model-provider-bridge", "api", "worker", "dashboard")
        }
        "down" {
            Invoke-OsiiCompose @("down")
        }
        "logs" {
            Invoke-OsiiCompose @("logs", "-f")
        }
        "build" {
            Invoke-OsiiCompose @("build", "api", "dashboard", "local-extractor")
        }
        "push-release" {
            if ($ImagePrefix.StartsWith("localhost/")) {
                throw "Set -ImagePrefix to a registry path such as quay.io/your-org/osii."
            }
            Invoke-OsiiCompose @("push", "api", "dashboard", "local-extractor")
        }
        "doctor" {
            & uv run --no-project --python $PythonVersion python scripts/disk_usage.py
        }
    }
}
finally {
    Pop-Location
}
