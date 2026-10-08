$RepoDir = "C:\Users\Ramy\Documents\polymarket-crypto"
$LogDir = "D:\polymarket-real-calibration\live"
$ReportFile = "$LogDir\SIM_24H_REPORT.txt"
$StartTime = [DateTime]::UtcNow
$MaxAge = 24 * 3600
$MaxRestarts = 100
$RestartCount = 0

Write-Host "=============================================="
Write-Host " 24h SIMULATION - Bonereaper Tactic"
Write-Host " Started: $($StartTime.ToString('yyyy-MM-dd HH:mm:ss')) UTC"
Write-Host " Will run until: $($StartTime.AddHours(24).ToString('yyyy-MM-dd HH:mm:ss')) UTC"
Write-Host "=============================================="

"SIMULATION 24H - Started $($StartTime.ToString('yyyy-MM-dd HH:mm:ss')) UTC" | Out-File $ReportFile -Encoding UTF8
"Capital: 109.16 | Tactic: Bonereaper (fair price, hold to resolution)" | Out-File $ReportFile -Encoding UTF8 -Append
"Markets: BTC, ETH, SOL, XRP, DOGE (5m)" | Out-File $ReportFile -Encoding UTF8 -Append
"---" | Out-File $ReportFile -Encoding UTF8 -Append

while ($RestartCount -lt $MaxRestarts) {
    $Age = [DateTime]::UtcNow - $StartTime
    if ($Age.TotalSeconds -ge $MaxAge) {
        Write-Host "24h reached. Stopping."
        "24h COMPLETE - $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')) UTC" | Out-File $ReportFile -Encoding UTF8 -Append
        break
    }

    $RestartCount++
    Write-Host ""
    Write-Host "--- Launch #$RestartCount (age: $($Age.ToString('hh\:mm\:ss'))) ---" -ForegroundColor Cyan

    # Clean
    taskkill /F /IM python.exe 2>$null
    Start-Sleep -Seconds 2
    Remove-Item -Force "$LogDir\STOP_MULTI" -ErrorAction SilentlyContinue
    Get-ChildItem "$LogDir\multi-v1-*" -ErrorAction SilentlyContinue | Remove-Item -Force

    $RunStart = [DateTime]::UtcNow
    $OutputFile = "$LogDir\sim_out_$($RunStart.ToString('yyyyMMdd_HHmmss')).log"

    try {
        Set-Location $RepoDir
        $process = Start-Process -FilePath "python" -ArgumentList "-m analysis.d6.real_execution_calibration_v1.multi_runner --simulate" -NoNewWindow -RedirectStandardOutput $OutputFile -RedirectStandardError "${OutputFile}_err" -PassThru
        $process.WaitForExit(7200)  # Wait up to 2h per run
        
        if (-not $process.HasExited) {
            $process.Kill()
            Write-Host "Killed after 2h timeout" -ForegroundColor Yellow
        }
        
        $ExitCode = $process.ExitCode
        Write-Host "Simulation exited with code $ExitCode" -ForegroundColor Yellow

        # Extract PnL from output
        if (Test-Path $OutputFile) {
            $Content = Get-Content $OutputFile -Tail 100
            $SummaryLines = $Content | Select-String -Pattern "SIMULATION|PnL|Wins|Losses|resolved|RESOLVED|PENDING|Total value|total_value" -SimpleMatch
            if ($SummaryLines) {
                $SummaryLines | ForEach-Object { $_ | Out-File $ReportFile -Encoding UTF8 -Append }
            }
        }

        "--- Exit #$RestartCount at $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')) (exit=$ExitCode) ---" | Out-File $ReportFile -Encoding UTF8 -Append

    } catch {
        Write-Host "CRASH: $_" -ForegroundColor Red
        "--- CRASH #$RestartCount at $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')): $_ ---" | Out-File $ReportFile -Encoding UTF8 -Append
    }

    $Age = [DateTime]::UtcNow - $StartTime
    if ($Age.TotalSeconds -ge $MaxAge) {
        "24h COMPLETE - $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')) UTC" | Out-File $ReportFile -Encoding UTF8 -Append
        break
    }

    Write-Host "Restarting in 5s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " 24h SIMULATION COMPLETE" -ForegroundColor Green
Write-Host " Report: $ReportFile" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
