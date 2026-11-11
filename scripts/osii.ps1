[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "dev", "demo", "demo-data", "doctor")]
    [string]$Command = "dev",
    [string]$SourceDir = "",
    [string]$RuntimeDir = "",
    [string]$PythonVersion = "3.12",
    [string]$EnvFile = ".env",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
if ($Command -eq "help") {
    Write-Host ".\scripts\osii.ps1 dev        Start OSII and all processor modules services"
    Write-Host ".\scripts\osii.ps1 demo       Add sample data, then start OSII"
    Write-Host ".\scripts\osii.ps1 doctor     Report disk usage"
    Write-Host "Optional: -EnvFile <file> -SourceDir <folder> -RuntimeDir <folder> -DryRun"
    exit 0
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Install uv and Node.js 22 or newer before starting OSII."
}
Push-Location $RepositoryRoot
$StartupNames = @("UV_SYSTEM_CERTS", "UV_NATIVE_TLS", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "PIP_CERT", "NODE_EXTRA_CA_CERTS")
$StartupOriginal = @{}
foreach ($Name in $StartupNames) {
    $StartupOriginal[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
}
try {
    # Import literal trust settings before the first uv call: Python may not exist.
    $DotEnvPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $RepositoryRoot $EnvFile }
    if ($EnvFile -ne ".env" -and -not (Test-Path -LiteralPath $DotEnvPath -PathType Leaf)) {
        throw "Startup env file not found: $EnvFile"
    }
    if (Test-Path -LiteralPath $DotEnvPath -PathType Leaf) {
        foreach ($Line in Get-Content -LiteralPath $DotEnvPath -Encoding UTF8) {
            if ($Line -notmatch '^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$') { continue }
            $Name, $Value = $Matches[1], $Matches[2]
            if ($Name -cnotin $StartupNames -or $null -ne $StartupOriginal[$Name]) { continue }
            if ($Value.StartsWith('"') -or $Value.StartsWith("'")) {
                if ($Value -notmatch '^(?:"([^"]*)"|''([^'']*)'')\s*(?:#.*)?$') {
                    throw "Invalid $Name in .env: use one literal value with matching quotes."
                }
                $Value = if ($null -ne $Matches[1]) { $Matches[1] } else { $Matches[2] }
            } else {
                $Value = ($Value -split '#', 2)[0].TrimEnd()
            }
            [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
        }
    }
    if ($env:SSL_CERT_FILE) {
        if (-not (Test-Path -LiteralPath $env:SSL_CERT_FILE -PathType Leaf) -or
            -not (Select-String -LiteralPath $env:SSL_CERT_FILE -Pattern '^-----BEGIN CERTIFICATE-----' -Quiet)) {
            throw "SSL_CERT_FILE must point to a readable PEM CA bundle. Use an absolute path; DER .crt files must be exported as PEM."
        }
    }
    $env:OSII_PYTHON_VERSION = $PythonVersion
    $env:OSII_STARTUP_ENV = $EnvFile
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
    foreach ($Name in $StartupNames) {
        if ($null -eq $StartupOriginal[$Name]) {
            Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($Name, $StartupOriginal[$Name], "Process")
        }
    }
    Pop-Location
}
