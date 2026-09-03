param(
    [string]$ImageName = "minilm-embedding-service",
    [int]$HostPort = 8085,
    [int]$ContainerPort = 8085
)

$ErrorActionPreference = "Stop"

Write-Host "Running Podman image: $ImageName"
podman run --rm -p "${HostPort}:${ContainerPort}" $ImageName
