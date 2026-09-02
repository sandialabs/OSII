[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("dev", "demo-data", "run", "build", "push-release", "down", "logs", "doctor")]
    [string]$Command = "dev",

    [ValidateSet("Podman", "Docker")]
    [string]$Runtime = "Podman",

    [string]$ImagePrefix = "",

    [string]$ImageTag = "latest",

    [switch]$InsecureRegistries,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$env:UV_PROJECT_ENVIRONMENT = Join-Path $RepositoryRoot "osii-env"
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
if (-not $ImagePrefix) {
    $ImagePrefix = if ($env:OSII_IMAGE_PREFIX) { $env:OSII_IMAGE_PREFIX } else { "localhost/osii" }
}
$env:OSII_IMAGE_PREFIX = $ImagePrefix
$env:OSII_IMAGE_TAG = $ImageTag

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
    & $ComposeExecutable @ComposePrefix @SecurityArguments @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Compose command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-OsiiDevLauncher {
    param([string[]]$Arguments = @())

    $UvExecutable = Get-Command "uv" -ErrorAction SilentlyContinue
    if (-not $UvExecutable) {
        throw "uv was not found. The bare-metal developer workflow requires uv and Node.js/npm."
    }
    if (-not (Get-Command "npm" -ErrorAction SilentlyContinue)) {
        throw "npm was not found. The bare-metal developer workflow requires Node.js/npm."
    }

    $LauncherArguments = @($Arguments)
    if ($DryRun) {
        $LauncherArguments += "--dry-run"
    }
    & $UvExecutable.Source run --no-project --python 3.11 python scripts/dev_stack.py @LauncherArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Bare-metal development stack exited with code $LASTEXITCODE. Review the first [dev] service error above for the cause."
    }
}

function Import-OsiiExampleData {
    $UvExecutable = Get-Command "uv" -ErrorAction SilentlyContinue
    if (-not $UvExecutable) {
        throw "uv was not found. Importing the example datasets requires uv and Python 3.11."
    }
    & $UvExecutable.Source run --no-project --python 3.11 --with "scikit-learn>=1.5,<2" python scripts/import_example_data.py
    if ($LASTEXITCODE -ne 0) {
        throw "Example data import exited with code $LASTEXITCODE."
    }
}

Push-Location $RepositoryRoot
try {
    switch ($Command) {
        "dev" {
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
            & uv run --no-project --python 3.11 python scripts/disk_usage.py
        }
    }
}
finally {
    Pop-Location
}
