[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("dev", "dev-host", "dev-core", "dev-ollama", "dev-openai", "dev-extractor", "dev-synthesizer", "dev-embedder", "dev-enricher", "dev-model-bridge", "dev-ocr-host", "dev-tika", "dev-containers", "dev-services", "dev-examples", "containers-dev", "run", "dev-all", "down", "logs", "build", "build-release", "push-release", "doctor", "catalog-rebuild", "catalog-verify", "provider-check")]
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
        "dev-openai" {
            Invoke-OsiiDevLauncher @("--provider-profile", "openai")
        }
        "provider-check" {
            & uv run --no-project --python 3.11 python scripts/check_openai_endpoint.py
            if ($LASTEXITCODE -ne 0) {
                throw "Commercial provider check failed with exit code $LASTEXITCODE."
            }
        }
        "dev-extractor" {
            & uv run --python 3.11 --package osii-local-extractor python -m uvicorn app.main:app --app-dir services/local-extractor --host 127.0.0.1 --port 8092 --reload
        }
        "dev-synthesizer" {
            & uv run --python 3.11 --package osii-local-synthesizer python -m uvicorn app.main:app --app-dir services/local-synthesizer --host 127.0.0.1 --port 8093 --reload
        }
        "dev-embedder" {
            & uv run --python 3.11 --package osii-local-embedder python -m uvicorn app.main:app --app-dir services/local-embedder --host 127.0.0.1 --port 8085 --reload
        }
        "dev-enricher" {
            & uv run --python 3.11 --package osii-local-enricher python -m uvicorn app.main:app --app-dir services/local-enricher --host 127.0.0.1 --port 8094 --reload
        }
        "dev-model-bridge" {
            & uv run --python 3.11 --package osii-model-provider-bridge python -m uvicorn app.main:app --app-dir services/model-provider-bridge --host 127.0.0.1 --port 8095 --reload
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
        "dev-tika" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika")
        }
        "dev-services" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
        }
        "run" {
            Invoke-OsiiCompose @("up", "--no-build", "--pull", "missing", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "model-provider-bridge", "api", "worker", "dashboard")
        }
        "dev-examples" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
            Invoke-OsiiCompose @("--profile", "examples", "up", "-d", "--build", "table-pdf-enricher")
            Invoke-OsiiDevLauncher @("--examples")
        }
        "containers-dev" {
            Invoke-OsiiCompose @("build", "api", "dashboard", "local-extractor")
            Invoke-OsiiCompose @("--profile", "agents", "--profile", "ocr", "build", "mcp", "tesseract")
            Invoke-OsiiCompose @("--profile", "agents", "--profile", "ocr", "up", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "model-provider-bridge", "api", "worker", "mcp", "dashboard", "tika", "tesseract")
        }
        "dev-all" {
            Invoke-OsiiCompose @("build", "api", "dashboard", "local-extractor")
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "agents", "--profile", "ocr", "build", "mcp", "table-pdf-enricher", "tesseract")
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "agents", "--profile", "ocr", "up")
        }
        "down" {
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "agents", "--profile", "ocr", "down")
        }
        "logs" {
            Invoke-OsiiCompose @("logs", "-f")
        }
        "build" {
            Invoke-OsiiCompose @("build", "api", "dashboard", "local-extractor")
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "agents", "--profile", "ocr", "build", "mcp", "table-pdf-enricher", "tesseract")
        }
        "build-release" {
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
