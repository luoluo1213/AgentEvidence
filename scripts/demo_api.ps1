param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Query = "Compare the reasoning mechanisms of ReAct and Reflexion."
)

$body = @{
    query = $Query
    session_id = "powershell-demo"
} | ConvertTo-Json

Write-Host "Health:"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/health" | ConvertTo-Json

Write-Host "`nJSON research response:"
Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl/api/v1/research" `
    -ContentType "application/json" `
    -Body $body | ConvertTo-Json -Depth 10

Write-Host "`nSSE stream (stage-level):"
curl.exe -N `
    -H "Content-Type: application/json" `
    -d $body `
    "$BaseUrl/api/v1/research/stream"
