param(
    [string]$ImageName = "minilm-embedding-service"
)

$ErrorActionPreference = "Stop"

Write-Host "Building Podman image: $ImageName"
podman build --format docker -t $ImageName .
