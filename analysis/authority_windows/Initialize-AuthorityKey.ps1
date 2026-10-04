[CmdletBinding()]
param([ValidatePattern('^v[1-9][0-9]*$')][string]$KeyVersion='v1')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$config=Get-Content -LiteralPath (Join-Path $root 'config\identity.json') -Raw | ConvertFrom-Json
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$sid=$identity.User.Value
if ($sid -ne $config.authority_sid -or $sid -eq $config.supervisor_sid) { throw 'DEDICATED_AUTHORITY_IDENTITY_REQUIRED' }
if (([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'NON_ADMIN_REQUIRED' }
$private=Join-Path $root 'private'
$acl=Get-Acl -LiteralPath $private
$rules=@($acl.Access)
if (-not $acl.AreAccessRulesProtected -or $rules.Count -ne 1 -or $rules[0].IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ne $sid -or $rules[0].AccessControlType -ne 'Allow') { throw 'PRIVATE_ACL_REQUIRED' }
$accessBefore=$acl.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access)
# Persist ONLY the owner section. Reapplying a Get-Acl descriptor through
# Set-Acl can request SACL privileges, which this identity must never receive.
$ownerOnly=[Security.AccessControl.DirectorySecurity]::new()
$ownerOnly.SetOwner($identity.User)
[IO.Directory]::SetAccessControl($private,$ownerOnly)
$after=[IO.Directory]::GetAccessControl($private)
if ($after.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid -or
    $after.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access) -cne $accessBefore) {
    throw 'OWNER_CHANGE_OR_DACL_INVARIANT_FAILED'
}
$keyPath=Join-Path $private ('authority-'+$KeyVersion+'.dpapi')
if (Test-Path -LiteralPath $keyPath) { throw 'KEY_ALREADY_EXISTS_NO_OVERWRITE' }
# Prove the new identity cannot read the actual wallet-secret file. Never print bytes.
$denied=$false
try { $stream=[IO.File]::OpenRead($config.main_env);$stream.Dispose() }
catch [UnauthorizedAccessException] { $denied=$true }
if (-not $denied) { throw 'WALLET_SECRET_ACCESS_NOT_DENIED' }
Add-Type -AssemblyName System.Security
$curve=[Security.Cryptography.ECCurve]::CreateFromFriendlyName('secP256k1')
$key=[Security.Cryptography.ECDsa]::Create($curve)
$parameters=$null
try {
    $parameters=$key.ExportParameters($true)
    $cipher=[Security.Cryptography.ProtectedData]::Protect($parameters.D,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    $file=[IO.File]::Open($keyPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {$file.Write($cipher,0,$cipher.Length);$file.Flush($true)} finally {$file.Dispose()}
    $restored=[Security.Cryptography.ProtectedData]::Unprotect($cipher,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    try {
        $difference=$restored.Length -bxor $parameters.D.Length
        for ($i=0;$i -lt $restored.Length;$i++) {$difference=$difference -bor ($restored[$i] -bxor $parameters.D[$i])}
        if ($difference -ne 0) {throw 'DPAPI_ROUNDTRIP'}
    }
    finally {[Array]::Clear($restored,0,$restored.Length)}
    # A separate non-secret random canary allows cross-user DPAPI denial testing.
    $canary=New-Object byte[] 32
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try {$rng.GetBytes($canary)} finally {$rng.Dispose()}
    $canaryCipher=[Security.Cryptography.ProtectedData]::Protect($canary,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    [Array]::Clear($canary,0,$canary.Length)
    [IO.File]::WriteAllBytes((Join-Path $root 'out\dpapi-canary.bin'),$canaryCipher)
    $public='0x04'+[BitConverter]::ToString($parameters.Q.X).Replace('-','').ToLower()+[BitConverter]::ToString($parameters.Q.Y).Replace('-','').ToLower()
    [ordered]@{schema='D6_AUTHORITY_PUBLIC_BOOTSTRAP_V1';authority_sid=$sid;supervisor_sid=$config.supervisor_sid;public_key=$public;key_file=('private/authority-'+$KeyVersion+'.dpapi');key_version=$KeyVersion;dpapi_roundtrip=$true;wallet_secret_access_denied=$true;approved=$false;production_proofs_signed=0} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'out\public-identity.json') -Encoding UTF8
    Write-Output 'KEY_CREATED_UNAPPROVED; PUBLIC_IDENTITY_EXPORTED; WALLET_SECRET_ACCESS_DENIED'
} finally {if ($null -ne $parameters) {[Array]::Clear($parameters.D,0,$parameters.D.Length)};$key.Dispose()}
