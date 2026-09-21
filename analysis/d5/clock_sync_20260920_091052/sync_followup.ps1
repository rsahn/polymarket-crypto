$ErrorActionPreference='Stop'
$d5Evidence='C:\Users\Ramy\Documents\polymarket-crypto\analysis\d5\clock_sync_20260920_091052'
Start-Transcript -LiteralPath (Join-Path $d5Evidence 'windows_sync_followup.txt') -NoClobber
w32tm /query /configuration
w32tm /resync
$d5Result=$LASTEXITCODE
w32tm /query /status /verbose
w32tm /stripchart /computer:time.windows.com /samples:5 /period:2 /dataonly
w32tm /stripchart /computer:time.cloudflare.com /samples:5 /period:2 /dataonly
[pscustomobject]@{ResyncExit=$d5Result;FinishedUtc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $d5Evidence 'followup_result.json') -Encoding utf8
Stop-Transcript
