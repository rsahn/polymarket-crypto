[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Stage,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ManifestSha256,
    [switch]$Apply,
    [switch]$UpdateHostOnly,
    [ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedInstalledManifestSha256
)
$ErrorActionPreference='Stop'
$root='C:\ProgramData\D6Authority'
$target=Join-Path $root 'runtime-v1'
$stagePath=(Resolve-Path -LiteralPath $Stage).Path
function Assert-NoLinks([string]$path) {
    $item=Get-Item -LiteralPath $path -Force
    while ($null -ne $item) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'REPARSE_POINT'}
        if ($item -is [IO.FileInfo]) {$item=$item.Directory} else {$item=$item.Parent}
    }
}
Assert-NoLinks $stagePath
Assert-NoLinks $root
$manifestPath=Join-Path $stagePath 'manifest.json'
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ManifestSha256) {throw 'MANIFEST_PIN_MISMATCH'}
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$identity=Get-Content -LiteralPath (Join-Path $root 'config\identity.json') -Raw | ConvertFrom-Json
if ($manifest.authority_sid -ne $identity.authority_sid -or $manifest.supervisor_sid -ne $identity.supervisor_sid) {throw 'SID_BINDING'}
if ($manifest.policy_digest -cne '0f5222753756d6dba1cb72951308f43ede74c6ef116391c44875bc17f1a67b3c') {throw 'POLICY_PIN'}
if (Test-Path -LiteralPath $target) {
    if (-not $UpdateHostOnly) {throw 'RUNTIME_ALREADY_EXISTS_NO_OVERWRITE'}
    Assert-NoLinks $target
    if (-not $ExpectedInstalledManifestSha256 -or
        (Get-FileHash -LiteralPath (Join-Path $target 'manifest.json')).Hash.ToLowerInvariant() -cne $ExpectedInstalledManifestSha256) {throw 'INSTALLED_MANIFEST_PIN'}
} elseif ($UpdateHostOnly) {throw 'EXISTING_RUNTIME_REQUIRED'}
# Validate the entire staged file inventory before any mutation.
$entries=@($manifest.files.PSObject.Properties)
foreach ($entry in $entries) {
    $relative=$entry.Name
    if ([IO.Path]::IsPathRooted($relative) -or $relative.Contains(':') -or (($relative -split '[\\/]') -contains '..')) {throw 'MANIFEST_PATH'}
    $source=[IO.Path]::GetFullPath((Join-Path $stagePath $relative))
    if (-not $source.StartsWith($stagePath.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'SOURCE_PATH_ESCAPE'}
    Assert-NoLinks $source
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {throw 'STAGED_FILE_CHANGED'}
}
if ($UpdateHostOnly) {
    foreach ($entry in $entries) {
        if ($entry.Name -ne 'telemetry_host.py' -and
            (Get-FileHash -LiteralPath (Join-Path $target $entry.Name)).Hash.ToLowerInvariant() -cne $entry.Value) {throw 'HOST_ONLY_UPDATE_REQUIRED'}
    }
}
if (-not $Apply) {
    [ordered]@{Target=$target;Files=$entries.Count;ManifestSha256=$ManifestSha256;PolicyDigest=$manifest.policy_digest;PrivateKeyTouched=$false;StartsProducer=$false;Validated=$true} | ConvertTo-Json
    return
}
$who=[Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($who)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {throw 'ADMINISTRATOR_REQUIRED'}
if ($UpdateHostOnly) {
    # Capture and recheck bytes before atomic replacement. Never touch the key.
    foreach ($name in @('telemetry_host.py','manifest.json')) {
        $bytes=[IO.File]::ReadAllBytes((Join-Path $stagePath $name))
        $expected=if ($name -eq 'manifest.json') {$ManifestSha256} else {$manifest.files.'telemetry_host.py'}
        $sha=[Security.Cryptography.SHA256]::Create()
        try {$actual=[BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose()}
        if ($actual -cne $expected) {throw 'UPDATE_BYTES_CHANGED'}
        $temporary=Join-Path $target ($name+'.new')
        $file=[IO.File]::Open($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {$file.Write($bytes,0,$bytes.Length);$file.Flush($true)} finally {$file.Dispose()}
        [IO.File]::Replace($temporary,(Join-Path $target $name),$null)
    }
    & (Join-Path $target 'python\python.exe') -I -S -B (Join-Path $target 'telemetry_host.py') --check-imports
    if ($LASTEXITCODE -ne 0) {throw 'ISOLATED_IMPORT_CHECK_FAILED'}
    Write-Output 'PROTECTED_HOST_UPDATED; PRODUCER_NOT_STARTED; KEY_UNCHANGED'
    return
}
$acl=[Security.AccessControl.DirectorySecurity]::new()
$acl.SetSecurityDescriptorSddlForm("O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FRFX;;;$($identity.authority_sid))(A;OICI;FRFX;;;$($identity.supervisor_sid))")
[IO.Directory]::CreateDirectory($target,$acl) | Out-Null
foreach ($entry in $entries) {
    $destination=[IO.Path]::GetFullPath((Join-Path $target $entry.Name))
    if (-not $destination.StartsWith($target+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'DESTINATION_PATH_ESCAPE'}
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
    [IO.File]::Copy((Join-Path $stagePath $entry.Name),$destination,$false)
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {throw 'DEPLOYED_FILE_CHANGED'}
}
[IO.File]::Copy($manifestPath,(Join-Path $target 'manifest.json'),$false)
if ((Get-FileHash -LiteralPath (Join-Path $target 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ManifestSha256) {throw 'DEPLOYED_MANIFEST_CHANGED'}
# Only import/configuration validation; no key is loaded and no network is used.
& (Join-Path $target 'python\python.exe') -I -S -B (Join-Path $target 'telemetry_host.py') --check-imports
if ($LASTEXITCODE -ne 0) {throw 'ISOLATED_IMPORT_CHECK_FAILED'}
Write-Output 'PROTECTED_RUNTIME_INSTALLED; PRODUCER_NOT_STARTED; KEY_UNCHANGED'
