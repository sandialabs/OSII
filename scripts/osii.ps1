[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "dev", "dev-shared", "demo", "demo-data", "run", "run-shared", "build", "push-release", "down", "logs", "doctor")]
    [string]$Command = "dev",

    [ValidateSet("Podman", "Docker")]
    [string]$Runtime = "Podman",

    [string]$ImagePrefix = "",

    [string]$ImageTag = "latest",

    [string]$BaseImage = "",

    [string]$PythonVersion = "",

    [string]$CaBundle = "",

    [string]$SourceDir = "",

    [string]$RuntimeDir = "",

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
if (-not $PythonVersion) {
    $PythonVersion = if ($env:OSII_PYTHON_VERSION) { $env:OSII_PYTHON_VERSION } else { "3.12" }
}
if (-not $CaBundle -and $env:OSII_CA_BUNDLE) {
    $CaBundle = $env:OSII_CA_BUNDLE
}
if ($SourceDir) {
    $env:OSII_SOURCE_DIR = $SourceDir
}
if ($RuntimeDir) {
    $env:OSII_RUNTIME_DIR = $RuntimeDir
}
$env:OSII_IMAGE_PREFIX = $ImagePrefix
$env:OSII_IMAGE_TAG = $ImageTag
$env:OSII_BASE_IMAGE = $BaseImage
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

function Test-OsiiCaBundle {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "CA bundle is not a readable file: $Path"
    }
    $ResolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $Bytes = [System.IO.File]::ReadAllBytes($ResolvedPath)
    if ($Bytes.Length -eq 0) {
        throw "CA bundle is empty."
    }
    if ($Bytes.Length -gt 10MB) {
        throw "CA bundle is larger than 10 MiB."
    }

    $Contents = [System.Text.Encoding]::ASCII.GetString($Bytes)
    if ($Contents -match "-----BEGIN [^-\r\n]*PRIVATE KEY-----") {
        throw "CA bundle contains a private key; provide public certificates only."
    }
    $Certificates = [regex]::Matches(
        $Contents,
        "-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----",
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    if ($Certificates.Count -eq 0) {
        throw "CA bundle does not contain a PEM CERTIFICATE block."
    }
    if (([regex]::Matches($Contents, "-----BEGIN CERTIFICATE-----")).Count -ne $Certificates.Count) {
        throw "CA bundle contains an incomplete CERTIFICATE block."
    }

    foreach ($CertificateMatch in $Certificates) {
        try {
            $Encoded = [regex]::Replace($CertificateMatch.Groups[1].Value, "\s+", "")
            $CertificateBytes = [Convert]::FromBase64String($Encoded)
            $Certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($CertificateBytes)
            if ($Certificate.HasPrivateKey) {
                throw "Certificate unexpectedly contains a private key."
            }
            $Certificate.Dispose()
        }
        catch {
            throw "CA bundle contains invalid PEM-encoded X.509 data: $($_.Exception.Message)"
        }
    }

    $Digest = (Get-FileHash -LiteralPath $ResolvedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "Validated $($Certificates.Count) public certificate(s). Bundle SHA-256: $Digest"
    return @{ Path = $ResolvedPath; Digest = $Digest }
}

function Assert-OsiiSharedDrive {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Shared drive is unavailable or is not a folder: $Path. Connect it in Windows, then try again."
    }
    try {
        Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop | Select-Object -First 1 | Out-Null
    }
    catch {
        throw "Shared drive cannot be read: $Path. $($_.Exception.Message)"
    }
}

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
    if ($CaBundle -and $ComposeAction -eq "build") {
        if ($Runtime -ne "Podman") {
            throw "-CaBundle requires Podman so the certificate file can be passed as a build secret."
        }
        $ValidatedBundle = Test-OsiiCaBundle -Path $CaBundle
        if ($ValidatedBundle.Path.Contains('"')) {
            throw "The CA bundle path cannot contain a double-quote character."
        }
        $CaBuildOptions = @(
            "--secret=id=osii_ca_bundle,src=`"$($ValidatedBundle.Path)`"",
            "--mount=type=secret,id=osii_ca_bundle",
            "--build-arg",
            "OSII_CA_BUNDLE_SHA256=$($ValidatedBundle.Digest)",
            "--env", "SSL_CERT_FILE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
            "--env", "REQUESTS_CA_BUNDLE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
            "--env", "CURL_CA_BUNDLE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
            "--env", "PIP_CERT=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
            "--env", "UV_NATIVE_TLS=true",
            "--env", "NODE_EXTRA_CA_CERTS=/etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem"
        )
        $SecurityArguments += "--podman-build-args=$($CaBuildOptions -join ' ')"
    }
    try {
        & $ComposeExecutable @ComposePrefix @SecurityArguments @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Compose command failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        if ($ComposeAction -eq "build") {
            Get-ChildItem -LiteralPath $RepositoryRoot -Filter "podman-build-secret-*" -Recurse -File -ErrorAction SilentlyContinue |
                Remove-Item -Force -ErrorAction SilentlyContinue
        }
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
    Write-Host "  .\scripts\osii.ps1 dev-shared Start OSII against an already connected shared drive"
    Write-Host "  .\scripts\osii.ps1 run        Start previously built container images"
    Write-Host "  .\scripts\osii.ps1 run-shared Start images with an already connected shared drive"
    Write-Host "  .\scripts\osii.ps1 down       Stop the container deployment"
    Write-Host "  .\scripts\osii.ps1 doctor     Report disk usage; never deletes files"
    Write-Host ""
    Write-Host "Normal source development needs only 'demo' or 'dev'. Optional AI, Tika,"
    Write-Host "and non-bundled Toolbox services are connected from the Setup page."
    Write-Host "For direct-network Podman containers, add -DisableContainerProxies."
    Write-Host "To add local corporate trust during a build, add -CaBundle C:\path\to\roots.pem."
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
        "dev-shared" {
            if (-not $SourceDir) {
                throw "dev-shared requires -SourceDir with a mapped drive or UNC folder that Windows can already read."
            }
            Assert-OsiiSharedDrive -Path $SourceDir
            $env:OSII_SOURCE_DIR = $SourceDir
            $env:OSII_RUNTIME_DIR = if ($RuntimeDir) { $RuntimeDir } else { ".\osii-data\shared-drive" }
            $env:OSII_SOURCE_KIND = "shared"
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
            Invoke-OsiiCompose @("up", "-d", "--no-build", "--pull", "missing", "tesseract", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "model-provider-bridge", "api", "worker", "dashboard")
        }
        "run-shared" {
            if (-not $SourceDir) {
                throw "run-shared requires -SourceDir with a mapped drive or UNC folder that Windows and Podman can already read."
            }
            Assert-OsiiSharedDrive -Path $SourceDir
            $env:OSII_SOURCE_DIR = $SourceDir
            $env:OSII_SOURCE_KIND = "shared"
            Invoke-OsiiCompose @("up", "-d", "--no-build", "--pull", "missing", "tesseract", "local-extractor", "local-synthesizer", "local-embedder", "local-enricher", "model-provider-bridge", "api", "worker", "dashboard")
        }
        "down" {
            Invoke-OsiiCompose @("down")
        }
        "logs" {
            Invoke-OsiiCompose @("logs", "-f")
        }
        "build" {
            Invoke-OsiiCompose @("build", "api", "dashboard", "local-extractor", "tesseract")
        }
        "push-release" {
            if ($ImagePrefix.StartsWith("localhost/")) {
                throw "Set -ImagePrefix to a registry path such as quay.io/your-org/osii."
            }
            Invoke-OsiiCompose @("push", "api", "dashboard", "local-extractor", "tesseract")
        }
        "doctor" {
            & uv run --no-project --python $PythonVersion python scripts/disk_usage.py
        }
    }
}
finally {
    Pop-Location
}
