param(
    [string]$ImageName = "jina-embeddings-service"
)

$ErrorActionPreference = "Stop"

Write-Host "Building Docker image: $ImageName"
podman build -t $ImageName .