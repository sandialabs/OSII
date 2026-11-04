[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "dev", "demo", "demo-data", "doctor", "test", "docs")]
    [string]$Command = "dev",
    [string]$SourceDir = "",
    [string]$RuntimeDir = "",
    [string]$PythonVersion = "3.12",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
if ($Command -eq "help") {
    Write-Host ".\scripts\osii.ps1 dev        Start configured local PostgreSQL and OSII"
    Write-Host ".\scripts\osii.ps1 test       Run server/SDK tests and build the dashboard"
    Write-Host ".\scripts\osii.ps1 docs       Check documentation"
    Write-Host ".\scripts\osii.ps1 doctor     Report disk usage"
    Write-Host "Configure PostgreSQL and the model endpoint in .env. Optional: -SourceDir <folder> -DryRun"
    exit 0
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Install uv and Node.js 22 or newer before starting OSII."
}
Push-Location $RepositoryRoot
try {
    $env:OSII_PYTHON_VERSION = $PythonVersion
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $RepositoryRoot ".venv"
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    if ($SourceDir) { $env:OSII_SOURCE_DIR = $SourceDir }
    if ($RuntimeDir) { $env:OSII_RUNTIME_DIR = $RuntimeDir }
    if ($Command -eq "doctor") {
        & uv run --no-project --python $PythonVersion python scripts/disk_usage.py
    } elseif ($Command -eq "test") {
        & uv run --frozen --python $PythonVersion --package osii --extra server --extra dev python -m pytest osii-core/server-tests osii-core/processor-sdk/tests -q
        if ($LASTEXITCODE -ne 0) { throw "Server tests failed." }
        Push-Location osii-dashboard/dashboard
        try {
            & npm test --if-present
            if ($LASTEXITCODE -ne 0) { throw "Dashboard tests failed." }
            & npm run build
        } finally { Pop-Location }
    } elseif ($Command -eq "docs") {
        & uv run --no-project --python $PythonVersion python scripts/check_docs_links.py
        if ($LASTEXITCODE -ne 0) { throw "Documentation links failed." }
        & uv run --no-project --python $PythonVersion --with mkdocs-material mkdocs build --strict
    } else {
        if ($Command -in @("demo", "demo-data")) {
            Write-Host "Server datasets are provisioned by administrators; no files imported."
            if ($Command -eq "demo-data") { exit 0 }
        }
        if ($Command -ne "demo-data") {
            $Arguments = @("run", "--no-project", "--python", $PythonVersion, "python", "scripts/dev_stack.py")
            if ($DryRun) { $Arguments += "--dry-run" }
            & uv @Arguments
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "OSII exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
