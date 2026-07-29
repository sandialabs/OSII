param(
    [string]$ImageName = "jina-embeddings-service",
    [int]$HostPort = 8085,
    [int]$ContainerPort = 8085
)

$ErrorActionPreference = "Stop"

Write-Host "Running Docker image: $ImageName"
podman run --rm -p "${HostPort}:${ContainerPort}" $ImageName