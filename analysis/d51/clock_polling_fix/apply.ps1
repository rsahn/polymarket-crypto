$ErrorActionPreference='Stop'
$folder=$PSScriptRoot
$configKey='HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Config'
$parameterKey='HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Parameters'
$beforeConfig=Get-ItemProperty -LiteralPath $configKey
$beforeParameters=Get-ItemProperty -LiteralPath $parameterKey
if ($beforeParameters.Type -ne 'NTP' -or $beforeParameters.NtpServer -ne 'time.windows.com,0x9' -or $beforeConfig.MinPollInterval -ne 10 -or $beforeConfig.MaxPollInterval -ne 15) { throw 'Unexpected configuration; no changes applied' }
if (Test-Path (Join-Path $folder 'apply_result.json')) { throw 'Already attempted; inspect evidence first' }
$before=@{Type=$beforeParameters.Type;NtpServer=$beforeParameters.NtpServer;MinPollInterval=$beforeConfig.MinPollInterval;MaxPollInterval=$beforeConfig.MaxPollInterval;captured_utc=[DateTime]::UtcNow.ToString('o')}
$before | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder 'before.json') -Encoding UTF8
$result=@{started_utc=[DateTime]::UtcNow.ToString('o');manual_clock_set=$false;status='STARTED'}
try {
 Set-ItemProperty -LiteralPath $configKey -Name MinPollInterval -Value 6
 Set-ItemProperty -LiteralPath $configKey -Name MaxPollInterval -Value 9
 $configOutput=& "$env:SystemRoot\System32\w32tm.exe" /config /manualpeerlist:time.windows.com,0x8 /syncfromflags:manual /update 2>&1
 $result.config_exit=$LASTEXITCODE
 $result.config_output=($configOutput | Out-String)
 if ($LASTEXITCODE -ne 0) { throw 'w32tm config failed' }
 $resyncOutput=& "$env:SystemRoot\System32\w32tm.exe" /resync 2>&1
 $result.resync_exit=$LASTEXITCODE
 $result.resync_output=($resyncOutput | Out-String)
 if ($LASTEXITCODE -ne 0) { throw 'w32tm resync failed' }
 $result.status='APPLIED_PENDING_OBSERVATION'
} catch {
 $result.error=$_.Exception.Message
 Set-ItemProperty -LiteralPath $configKey -Name MinPollInterval -Value $before.MinPollInterval
 Set-ItemProperty -LiteralPath $configKey -Name MaxPollInterval -Value $before.MaxPollInterval
 $rollback=& "$env:SystemRoot\System32\w32tm.exe" /config /manualpeerlist:time.windows.com,0x9 /syncfromflags:manual /update 2>&1
 $result.rollback_exit=$LASTEXITCODE
 $result.rollback_output=($rollback | Out-String)
 $result.status='FAILED_ROLLBACK_ATTEMPTED'
} finally {
 $result.finished_utc=[DateTime]::UtcNow.ToString('o')
 $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $folder 'apply_result.json') -Encoding UTF8
 & "$env:SystemRoot\System32\w32tm.exe" /query /status /verbose *> (Join-Path $folder 'after_status.txt')
 & "$env:SystemRoot\System32\w32tm.exe" /query /configuration *> (Join-Path $folder 'after_configuration.txt')
}
