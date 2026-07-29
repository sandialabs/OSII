[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("dev", "run", "dev-examples", "dev-all", "down", "logs", "build")]
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

Push-Location $RepositoryRoot
try {
    switch ($Command) {
        "dev" {
            Invoke-OsiiCompose @("--profile", "chat", "--profile", "ocr", "up", "--build", "api", "worker", "dashboard", "chat", "tika", "tesseract")
        }
        "run" {
            Invoke-OsiiCompose @("--profile", "chat", "--profile", "ocr", "up", "api", "worker", "dashboard", "chat", "tika", "tesseract")
        }
        "dev-examples" {
            Invoke-OsiiCompose @("--profile", "examples", "up", "--build", "api", "dashboard", "table-pdf-enricher")
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
