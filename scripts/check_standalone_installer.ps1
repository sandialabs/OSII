param(
    [string]$Installer = "$PSScriptRoot/../release/standalone/OSII-Standalone-Setup.exe",
    [switch]$RequireSignature,
    [switch]$BlockExternalNetwork
)
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$nodeExecutable = (Get-Command node -ErrorAction Stop).Source
$testBase = if ($BlockExternalNetwork) { $env:ProgramData } else { $env:TEMP }
$testRoot = Join-Path $testBase ("OSII installer " + [Guid]::NewGuid().ToString())
$installation = Join-Path $testRoot 'Installed application'
$workspace = Join-Path $testRoot 'Preserved library'
$previousPath = $env:PATH
$previousExecutable = $env:OSII_DESKTOP_EXECUTABLE
$previousWorkspace = $env:OSII_SMOKE_DIRECTORY
$previousOffline = $env:OSII_SMOKE_BLOCK_EXTERNAL
$firewallRules = [System.Collections.Generic.List[string]]::new()

function Install-OSII {
    $process = Start-Process -FilePath (Resolve-Path $Installer).Path -ArgumentList "/S /D=$installation" -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
    if (-not (Test-Path (Join-Path $installation 'OSII Standalone.exe'))) { throw 'Installed desktop executable is missing' }
}

function Block-OSIIOutbound([string]$Executable) {
    $program = (Resolve-Path -LiteralPath $Executable).ProviderPath
    $ruleName = "OSII-installer-test-" + [Guid]::NewGuid().ToString()
    New-NetFirewallRule -Name $ruleName -DisplayName $ruleName -Program $program `
        -Direction Outbound -Action Block | Out-Null
    $firewallRules.Add($ruleName)
    if (-not (Get-NetFirewallRule -PolicyStore ActiveStore -Name $ruleName)) {
        throw 'The outbound firewall rule is not active'
    }
}

try {
    New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
    if ($BlockExternalNetwork) {
        $probe = Invoke-WebRequest -Uri 'https://github.com/robots.txt' -TimeoutSec 15
        if ($probe.StatusCode -ne 200) { throw 'External connectivity control did not pass' }
        $testInstaller = Join-Path $testRoot 'OSII-Standalone-Setup.exe'
        Copy-Item -LiteralPath $Installer -Destination $testInstaller
        $Installer = $testInstaller
        Block-OSIIOutbound $Installer
    }
    Install-OSII
    if ($RequireSignature) {
        foreach ($file in @($Installer, (Join-Path $installation 'OSII Standalone.exe'), (Join-Path $installation 'resources/runtime/osii-runtime.exe'))) {
            if ((Get-AuthenticodeSignature $file).Status -ne 'Valid') { throw "Invalid release signature: $file" }
        }
    }
    $env:OSII_DESKTOP_EXECUTABLE = Join-Path $installation 'OSII Standalone.exe'
    $env:OSII_SMOKE_DIRECTORY = $workspace
    if ($BlockExternalNetwork) {
        # Program rules leave loopback and the Actions runner online.
        $programs = @($env:OSII_DESKTOP_EXECUTABLE,
            (Join-Path $installation 'resources/runtime/osii-runtime.exe'),
            (Join-Path $installation 'resources/runtime/_internal/embedding/llama-server.exe'))
        foreach ($program in $programs) {
            Block-OSIIOutbound $program
        }
        $env:OSII_SMOKE_BLOCK_EXTERNAL = '1'
    }
    # The test driver uses an explicit Node path. The installed app cannot find
    # Python, uv, npm, Java or a system OCR engine through this environment.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    & $nodeExecutable (Join-Path $repository 'osii-desktop/tests/smoke.cjs')
    if ($LASTEXITCODE -ne 0) { throw 'Installed application smoke test failed' }
    Install-OSII
    & $nodeExecutable (Join-Path $repository 'osii-desktop/tests/smoke.cjs')
    if ($LASTEXITCODE -ne 0) { throw 'Reinstalled application did not preserve its library' }
    $evidence = @(Get-ChildItem (Join-Path $workspace 'application/libraries') -Recurse -File)
    if ($evidence.Count -eq 0) { throw 'No persisted library evidence was found' }
    $before = @{}
    foreach ($file in $evidence) { $before[$file.FullName] = (Get-FileHash $file.FullName -Algorithm SHA256).Hash }
    $uninstaller = Get-ChildItem $installation -Filter 'Uninstall*.exe' -File | Select-Object -First 1
    if (-not $uninstaller) { throw 'NSIS uninstaller was not created' }
    $process = Start-Process -FilePath $uninstaller.FullName -ArgumentList '/S' -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Uninstaller failed' }
    $deadline = (Get-Date).AddSeconds(30)
    while ((Test-Path $env:OSII_DESKTOP_EXECUTABLE) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250 }
    if (Test-Path $env:OSII_DESKTOP_EXECUTABLE) { throw 'Uninstaller left the application executable installed' }
    foreach ($file in $evidence) {
        if (-not (Test-Path $file.FullName)) { throw 'Uninstall deleted library evidence' }
        if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $before[$file.FullName]) { throw 'Uninstall changed library evidence' }
    }
    Write-Output 'Installer, first run, reinstall, restart, and data-preserving uninstall passed.'
} finally {
    $env:PATH = $previousPath
    $env:OSII_DESKTOP_EXECUTABLE = $previousExecutable
    $env:OSII_SMOKE_DIRECTORY = $previousWorkspace
    $env:OSII_SMOKE_BLOCK_EXTERNAL = $previousOffline
    foreach ($ruleName in $firewallRules) {
        Remove-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    }
    if (Test-Path $testRoot) { Remove-Item -Recurse -Force $testRoot }
}
