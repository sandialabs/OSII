[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("dev", "dev-host", "dev-core", "dev-ollama", "dev-corporate", "dev-extractor", "dev-synthesizer", "dev-embedder", "dev-enricher", "dev-model-bridge", "dev-ocr-host", "dev-containers", "dev-services", "dev-examples", "containers-dev", "run", "dev-all", "down", "logs", "build", "doctor", "catalog-rebuild", "catalog-verify")]
    [string]$Command = "dev",

    [ValidateSet("Podman", "Docker")]
    [string]$Runtime = "Podman",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$env:UV_PROJECT_ENVIRONMENT = Join-Path $RepositoryRoot "osii-env"
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

if ($Runtime -eq "Docker") {
    $ComposeExecutable = "docker"
    $ComposePrefix = @("compose")
}
else {
    $ComposeExecutable = "podman-compose"
    $ComposePrefix = @()
}

function Invoke-OsiiCompose {
    param([string[]]$Arguments)
    if (-not (Get-Command $ComposeExecutable -ErrorAction SilentlyContinue)) {
        throw "$ComposeExecutable was not found. Install $Runtime Desktop/CLI, then try again."
    }
    & $ComposeExecutable @ComposePrefix @Arguments
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
        throw "Bare-metal development stack exited with code $LASTEXITCODE."
    }
}

Push-Location $RepositoryRoot
try {
    switch ($Command) {
        "dev" {
            Invoke-OsiiDevLauncher
        }
        "dev-host" {
            Invoke-OsiiDevLauncher
        }
        "dev-core" {
            Invoke-OsiiDevLauncher @("--core-only")
        }
        "dev-ollama" {
            Invoke-OsiiDevLauncher @("--provider-profile", "ollama")
        }
        "dev-corporate" {
            Invoke-OsiiDevLauncher @("--provider-profile", "corporate")
        }
        "dev-extractor" {
            & uv run --python 3.11 --package osii-local-extractor uvicorn app.main:app --app-dir services/local-extractor --host 127.0.0.1 --port 8092 --reload
        }
        "dev-synthesizer" {
            & uv run --python 3.11 --package osii-local-synthesizer uvicorn app.main:app --app-dir services/local-synthesizer --host 127.0.0.1 --port 8093 --reload
        }
        "dev-embedder" {
            & uv run --python 3.11 --package osii-local-embedder uvicorn app.main:app --app-dir services/local-embedder --host 127.0.0.1 --port 8085 --reload
        }
        "dev-enricher" {
            & uv run --python 3.11 --package osii-local-enricher uvicorn app.main:app --app-dir services/local-enricher --host 127.0.0.1 --port 8094 --reload
        }
        "dev-model-bridge" {
            & uv run --python 3.11 --package osii-model-provider-bridge uvicorn app.main:app --app-dir services/model-provider-bridge --host 127.0.0.1 --port 8095 --reload
        }
        "dev-ocr-host" {
            $env:ENABLE_DEMO = "true"
            Push-Location (Join-Path $RepositoryRoot "ai-ready-tool-shelf/osii-tesseract")
            try {
                & uv run --no-project --python 3.11 --with-requirements requirements.txt python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
            }
            finally {
                Pop-Location
            }
        }
        "dev-containers" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
            Invoke-OsiiDevLauncher
        }
        "dev-services" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
        }
        "run" {
            Invoke-OsiiCompose @("--profile", "chat", "--profile", "agents", "--profile", "ocr", "up", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "model-provider-bridge", "api", "worker", "chat", "mcp", "dashboard", "tika", "tesseract")
        }
        "dev-examples" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
            Invoke-OsiiCompose @("--profile", "examples", "up", "-d", "--build", "table-pdf-enricher")
            Invoke-OsiiDevLauncher @("--examples")
        }
        "containers-dev" {
            Invoke-OsiiCompose @("--profile", "chat", "--profile", "agents", "--profile", "ocr", "up", "--build", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "model-provider-bridge", "api", "worker", "chat", "mcp", "dashboard", "tika", "tesseract")
        }
        "dev-all" {
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "chat", "--profile", "agents", "--profile", "ocr", "up", "--build")
        }
        "down" {
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "chat", "--profile", "agents", "--profile", "ocr", "down")
        }
        "logs" {
            Invoke-OsiiCompose @("logs", "-f")
        }
        "build" {
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "chat", "--profile", "agents", "--profile", "ocr", "build")
        }
        "doctor" {
            & uv run --no-project --python 3.11 python scripts/disk_usage.py
        }
        "catalog-rebuild" {
            & uv run --python 3.11 --package osii python -m osii.catalog_cli rebuild
        }
        "catalog-verify" {
            & uv run --python 3.11 --package osii python -m osii.catalog_cli verify
        }
    }
}
finally {
    Pop-Location
}
