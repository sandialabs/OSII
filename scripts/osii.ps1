[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("dev", "dev-host", "dev-core", "dev-model2vec", "dev-extractor", "dev-synthesizer", "dev-embedder", "dev-enricher", "dev-containers", "dev-services", "dev-examples", "containers-dev", "run", "dev-all", "down", "logs", "build")]
    [string]$Command = "dev",

    [ValidateSet("Podman", "Docker")]
    [string]$Runtime = "Podman"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot

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

    & $UvExecutable.Source run --no-project --python 3.11 python scripts/dev_stack.py @Arguments
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
        "dev-model2vec" {
            Invoke-OsiiDevLauncher @("--model2vec")
        }
        "dev-extractor" {
            & uv run --package osii-local-extractor uvicorn app.main:app --app-dir services/local-extractor --host 127.0.0.1 --port 8092 --reload
        }
        "dev-synthesizer" {
            & uv run --package osii-local-synthesizer uvicorn app.main:app --app-dir services/local-synthesizer --host 127.0.0.1 --port 8093 --reload
        }
        "dev-embedder" {
            & uv run --package osii-local-embedder uvicorn app.main:app --app-dir services/local-embedder --host 127.0.0.1 --port 8085 --reload
        }
        "dev-enricher" {
            & uv run --package osii-local-enricher uvicorn app.main:app --app-dir services/local-enricher --host 127.0.0.1 --port 8094 --reload
        }
        "dev-containers" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
            Invoke-OsiiDevLauncher
        }
        "dev-services" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
        }
        "run" {
            Invoke-OsiiCompose @("--profile", "chat", "--profile", "ocr", "up", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "api", "worker", "chat", "dashboard", "tika", "tesseract")
        }
        "dev-examples" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
            Invoke-OsiiCompose @("--profile", "examples", "up", "-d", "--build", "table-pdf-enricher")
            Invoke-OsiiDevLauncher @("--examples")
        }
        "containers-dev" {
            Invoke-OsiiCompose @("--profile", "chat", "--profile", "ocr", "up", "--build", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "api", "worker", "chat", "dashboard", "tika", "tesseract")
        }
        "dev-all" {
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "chat", "--profile", "agents", "--profile", "ocr", "--profile", "embeddings", "--profile", "ollama", "up", "--build")
        }
        "down" {
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "chat", "--profile", "agents", "--profile", "ocr", "--profile", "embeddings", "--profile", "ollama", "down")
        }
        "logs" {
            Invoke-OsiiCompose @("logs", "-f")
        }
        "build" {
            Invoke-OsiiCompose @("--profile", "examples", "--profile", "chat", "--profile", "agents", "--profile", "ocr", "--profile", "embeddings", "build")
        }
    }
}
finally {
    Pop-Location
}
