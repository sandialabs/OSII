param(
    [string]$BaseUrl = "http://localhost:8085"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking health endpoint..."
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health"

Write-Host ""
Write-Host "Requesting embeddings..."
$body = @{
    texts = @(
        "Sandia develops advanced national security technologies.",
        "Embeddings map text into vector space."
    )
    normalize = $true
    batch_size = 8
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "$BaseUrl/embed" -ContentType "application/json" -Body $body