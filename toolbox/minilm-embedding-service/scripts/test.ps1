param(
    [string]$BaseUrl = "http://localhost:8085"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking health endpoint..."
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health"

Write-Host ""
Write-Host "Requesting embeddings..."
$body = @{
    input = @(
        "Sandia develops advanced national security technologies.",
        "Embeddings map text into vector space."
    )
    model = "sentence-transformers/all-MiniLM-L6-v2"
    encoding_format = "float"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/embeddings" -ContentType "application/json" -Body $body
