$ErrorActionPreference='Stop'
$d5Evidence='C:\Users\Ramy\Documents\polymarket-crypto\analysis\d5\clock_sync_20260920_091052'
Start-Transcript -LiteralPath (Join-Path $d5Evidence 'windows_sync_convergence.txt') -NoClobber
for ($d5Attempt=1; $d5Attempt -le 6; $d5Attempt++) {
    Write-Output "NTP_CONVERGENCE_ATTEMPT=$d5Attempt"
    w32tm /resync /soft
    w32tm /query /status /verbose
    w32tm /stripchart /computer:time.windows.com /samples:1 /dataonly
    if ($d5Attempt -lt 6) { Start-Sleep -Seconds 10 }
}
w32tm /stripchart /computer:time.cloudflare.com /samples:3 /period:1 /dataonly
Get-Service W32Time | Select-Object Name,Status,StartType | Format-List
Stop-Transcript
