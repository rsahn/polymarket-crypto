# Run explicitly by the human in elevated PowerShell. No D6 process is started.
# Temporarily request a clock step instead of gradual rate correction, then restore.
$ErrorActionPreference = 'Stop'
$clockIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$clockPrincipal = [Security.Principal.WindowsPrincipal]::new($clockIdentity)
if (-not $clockPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator PowerShell required.'
}
$clockConfigPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Config'
$clockPreviousOffset = (Get-ItemProperty -LiteralPath $clockConfigPath -Name MaxAllowedPhaseOffset).MaxAllowedPhaseOffset
Write-Output "Previous MaxAllowedPhaseOffset=$clockPreviousOffset seconds; restored in finally."
try {
    Set-ItemProperty -LiteralPath $clockConfigPath -Name MaxAllowedPhaseOffset -Value 0
    Start-Service W32Time
    w32tm /config /update
    if ($LASTEXITCODE -ne 0) { throw 'W32Time update failed.' }
    w32tm /resync /rediscover
    if ($LASTEXITCODE -ne 0) { throw 'W32Time resync failed.' }
    Start-Sleep -Seconds 15
    w32tm /query /status /verbose
    if ($LASTEXITCODE -ne 0) { throw 'W32Time status failed.' }
} finally {
    Set-ItemProperty -LiteralPath $clockConfigPath -Name MaxAllowedPhaseOffset -Value $clockPreviousOffset
    w32tm /config /update
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Original registry value restored; service update failed. Run w32tm /config /update.' }
}
Write-Output 'Clock resync is not qualification: rerun independent <=100ms measurements and StreamBook.'
