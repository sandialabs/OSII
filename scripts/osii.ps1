[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "dev", "demo", "demo-data", "doctor")]
    [string]$Command = "dev",
    [string]$SourceDir = "",
    [string]$RuntimeDir = "",
    [string]$PythonVersion = "3.12",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
if ($Command -eq "help") {
    Write-Host ".\scripts\osii.ps1 dev        Install dependencies and start OSII"
    Write-Host ".\scripts\osii.ps1 demo       Add sample data, then start OSII"
    Write-Host ".\scripts\osii.ps1 doctor     Report disk usage"
    Write-Host "Optional: -SourceDir <folder> -RuntimeDir <folder> -DryRun"
    exit 0
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Install uv and Node.js 22 or newer before starting OSII."
}
Push-Location $RepositoryRoot
try {
    $env:OSII_PYTHON_VERSION = $PythonVersion
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $RepositoryRoot "osii-env"
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    if ($SourceDir) { $env:OSII_SOURCE_DIR = $SourceDir }
    if ($RuntimeDir) { $env:OSII_RUNTIME_DIR = $RuntimeDir }
    if ($Command -eq "doctor") {
        & uv run --no-project --python $PythonVersion python scripts/disk_usage.py
    } else {
        if ($Command -in @("demo", "demo-data")) {
            & uv run --no-project --python $PythonVersion --with "scikit-learn>=1.5,<2" python scripts/import_example_data.py
            if ($LASTEXITCODE -ne 0) { throw "Example-data installation failed." }
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
