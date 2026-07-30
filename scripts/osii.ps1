[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("dev", "dev-embeddings", "dev-services", "dev-examples", "containers-dev", "run", "dev-all", "down", "logs", "build")]
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

if (-not (Get-Command $ComposeExecutable -ErrorAction SilentlyContinue)) {
    throw "$ComposeExecutable was not found. Install $Runtime Desktop/CLI, then try again."
}

function Invoke-OsiiCompose {
    param([string[]]$Arguments)
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
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
            Invoke-OsiiDevLauncher
        }
        "dev-embeddings" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
            Invoke-OsiiDevLauncher @("--embeddings")
        }
        "dev-services" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
        }
        "run" {
            Invoke-OsiiCompose @("--profile", "chat", "--profile", "ocr", "up", "embeddings", "api", "worker", "chat", "dashboard", "tika", "tesseract")
        }
        "dev-examples" {
            Invoke-OsiiCompose @("--profile", "ocr", "up", "-d", "tika", "tesseract")
            Invoke-OsiiCompose @("--profile", "examples", "up", "-d", "--build", "table-pdf-enricher")
            Invoke-OsiiDevLauncher @("--examples")
        }
        "containers-dev" {
            Invoke-OsiiCompose @("--profile", "chat", "--profile", "ocr", "up", "--build", "embeddings", "api", "worker", "chat", "dashboard", "tika", "tesseract")
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
