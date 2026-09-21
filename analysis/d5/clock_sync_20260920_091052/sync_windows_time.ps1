$ErrorActionPreference = 'Stop'
$d5Evidence = 'C:\Users\Ramy\Documents\polymarket-crypto\analysis\d5\clock_sync_20260920_091052'
try {
    Start-Transcript -LiteralPath (Join-Path $d5Evidence 'windows_sync_transcript.txt') -NoClobber
    Start-Service -Name W32Time
    w32tm /resync
    $d5SyncExit = $LASTEXITCODE
    w32tm /query /status /verbose
    $d5StatusExit = $LASTEXITCODE
    w32tm /query /source
    Get-Service W32Time | Select-Object Name,Status,StartType | Format-List
    [pscustomobject]@{ResyncExit=$d5SyncExit;StatusExit=$d5StatusExit;ServiceStatus=(Get-Service W32Time).Status.ToString();FinishedUtc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $d5Evidence 'sync_result.json') -Encoding utf8
    Stop-Transcript
    exit $d5SyncExit
} catch {
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $d5Evidence 'sync_error.txt') -Encoding utf8
    try { Stop-Transcript } catch {}
    exit 1
}
