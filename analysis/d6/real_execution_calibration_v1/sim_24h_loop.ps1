$RepoDir = "C:\Users\Ramy\Documents\polymarket-crypto"
$LogDir = "D:\polymarket-real-calibration\live"
$ReportFile = "$LogDir\SIM_24H_REPORT.txt"
$StartTime = [DateTime]::UtcNow
$MaxAge = 24 * 3600
$RestartCount = 0

Set-Location $RepoDir

# Initial report
$header = @"
SIMULATION 24H - Started $($StartTime.ToString('yyyy-MM-dd HH:mm:ss')) UTC
Capital: 100.00 | Tactic: Bonereaper (fair price, hold to resolution)
Markets: BTC, ETH, SOL, XRP, DOGE (5m)
---
"@
$header | Out-File $ReportFile -Encoding UTF8

while ($true) {
    $Age = [DateTime]::UtcNow - $StartTime
    if ($Age.TotalSeconds -ge $MaxAge) {
        "24h COMPLETE - $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')) UTC" | Out-File $ReportFile -Encoding UTF8 -Append
        exit 0
    }

    $RestartCount++
    $RunStart = [DateTime]::UtcNow
    $OutputFile = "$LogDir\sim_out_$($RunStart.ToString('yyyyMMdd_HHmmss')).log"
    $ErrorFile = "$LogDir\sim_err_$($RunStart.ToString('yyyyMMdd_HHmmss')).log"

    Write-Host "Launch #$RestartCount at $($RunStart.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Cyan

    try {
        $process = Start-Process -FilePath "python" -ArgumentList "-m analysis.d6.real_execution_calibration_v1.multi_runner --simulate" -NoNewWindow -RedirectStandardOutput $OutputFile -RedirectStandardError $ErrorFile -PassThru
        $process.WaitForExit(7200000)
        
        if (-not $process.HasExited) {
            $process.Kill()
        }
        
        $ExitCode = $process.ExitCode
        Write-Host "Exited code=$ExitCode" -ForegroundColor Yellow
        
        # Extract PnL lines
        if (Test-Path $OutputFile) {
            Get-Content $OutputFile -Tail 50 | Select-String -Pattern "SIMULATION|PnL|Wins|Losses|resolved|RESOLVED|PENDING|total_value|pnl=|cycle" -SimpleMatch | ForEach-Object { $_ | Out-File $ReportFile -Encoding UTF8 -Append }
        }
        
        "--- Exit #$RestartCount at $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')) (exit=$ExitCode) ---" | Out-File $ReportFile -Encoding UTF8 -Append
    }
    catch {
        Write-Host "CRASH: $_" -ForegroundColor Red
        "--- CRASH #$RestartCount at $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')): $_ ---" | Out-File $ReportFile -Encoding UTF8 -Append
    }

    $Age = [DateTime]::UtcNow - $StartTime
    if ($Age.TotalSeconds -ge $MaxAge) {
        "24h COMPLETE - $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')) UTC" | Out-File $ReportFile -Encoding UTF8 -Append
        exit 0
    }

    Start-Sleep -Seconds 3
}
