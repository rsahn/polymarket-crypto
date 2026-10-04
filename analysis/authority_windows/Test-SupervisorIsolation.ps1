[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$config=Get-Content -LiteralPath (Join-Path $root 'config\identity.json') -Raw | ConvertFrom-Json
$who=[Security.Principal.WindowsIdentity]::GetCurrent()
if ($who.User.Value -ne $config.supervisor_sid) {throw 'ACTUAL_SUPERVISOR_SID_REQUIRED'}
if (([Security.Principal.WindowsPrincipal]::new($who)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {throw 'SUPERVISOR_MUST_NOT_BE_ELEVATED'}
$public=Get-Content -LiteralPath (Join-Path $root 'out\public-identity.json') -Raw | ConvertFrom-Json
if (-not $public.dpapi_roundtrip -or $public.authority_sid -ne $config.authority_sid) {throw 'BOOTSTRAP_EVIDENCE_REQUIRED'}
$keyDenied=$false
if ($public.key_version -notmatch '^v[1-9][0-9]*$') {throw 'KEY_VERSION'}
try {$f=[IO.File]::OpenRead((Join-Path $root ('private\authority-'+$public.key_version+'.dpapi')));$f.Dispose()}
catch [UnauthorizedAccessException] {$keyDenied=$true}
$writeDenied=$true
foreach ($directory in @('bin','config','out','private')) {
    $probe=Join-Path $root ($directory+'\supervisor-access-probe-'+[Guid]::NewGuid().ToString('N'))
    try {$f=[IO.File]::Open($probe,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write);$f.Dispose();[IO.File]::Delete($probe);$writeDenied=$false}
    catch [UnauthorizedAccessException] {}
}
Add-Type -AssemblyName System.Security
$dpapiDenied=$false
$cipher=[IO.File]::ReadAllBytes((Join-Path $root 'out\dpapi-canary.bin'))
try {$plain=[Security.Cryptography.ProtectedData]::Unprotect($cipher,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser);[Array]::Clear($plain,0,$plain.Length)}
catch [Security.Cryptography.CryptographicException] {$dpapiDenied=$true}
$result=[ordered]@{supervisor_sid=$who.User.Value;authority_sid=$config.authority_sid;key_read_denied=$keyDenied;code_config_output_private_write_denied=$writeDenied;cross_user_dpapi_denied=$dpapiDenied;PASS=($keyDenied -and $writeDenied -and $dpapiDenied);production_qualified=$false}
$result | ConvertTo-Json
if (-not $result.PASS) {throw 'ISOLATION_FAILED'}
