[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$accountName = 'D6Authority'
$supervisorSid = 'S-1-5-21-996557404-12191610-680381608-1002'
$root = Join-Path $env:ProgramData 'D6Authority'
$plan = [ordered]@{
    Account=$accountName; Administrator=$false; SupervisorSid=$supervisorSid
    Root=$root; Private='Authority SID only, protected DACL, DPAPI CurrentUser'
    CodeAndConfig='Administrators/SYSTEM write; Authority and supervisor read/execute'
    Output='Authority modify; supervisor read; no inbound signing-request directory'
    AccountPassword='Interactive SecureString, not stored by this script'
    ProductionSigningEnabled=$false; WalletCredentialsCopied=$false
    ExistingAccountOrDirectory='Abort; never reuse or change existing ACLs'
}
if (-not $Apply) { $plan | ConvertTo-Json; return }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'ADMINISTRATOR_REQUIRED' }
if (Get-LocalUser -Name $accountName -ErrorAction SilentlyContinue) { throw 'ACCOUNT_ALREADY_EXISTS' }
if (Test-Path -LiteralPath $root) { throw 'DIRECTORY_ALREADY_EXISTS' }
$programDataItem = Get-Item -LiteralPath $env:ProgramData -Force
if (-not $programDataItem.PSIsContainer) { throw 'PROGRAMDATA_DIRECTORY_REQUIRED' }
if ($programDataItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'REPARSE_POINT' }
foreach ($name in @('Initialize-AuthorityKey.ps1','Test-SupervisorIsolation.ps1','policy-template.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $name))) { throw 'BUNDLE_INCOMPLETE' }
}
$password = Read-Host 'Nouveau mot de passe unique D6Authority (ne pas le coller dans le chat)' -AsSecureString
try {
    $newUser = New-LocalUser -Name $accountName -Password $password -Description 'D6 telemetry only; no wallet credentials'
} finally {
    $password.Dispose()
}
$authoritySid = $newUser.SID.Value
if ($authoritySid -eq $supervisorSid -or $authoritySid -eq $identity.User.Value) { throw 'IDENTITY_COLLISION' }
# A newly created local account has no privileged membership. Add Users only.
$users = Get-LocalGroup -SID 'S-1-5-32-545'
if (-not (Get-LocalGroupMember -Group $users | Where-Object {$_.SID.Value -eq $authoritySid})) {
    Add-LocalGroupMember -Group $users -Member $newUser
}
function New-ControlledDirectory([string]$path,[string]$sddl) {
    $security = [Security.AccessControl.DirectorySecurity]::new()
    $security.SetSecurityDescriptorSddlForm($sddl)
    [IO.Directory]::CreateDirectory($path,$security) | Out-Null
}
# Root read permissions do not inherit into the private directory.
New-ControlledDirectory $root "O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FRFX;;;$authoritySid)(A;;FRFX;;;$supervisorSid)"
New-ControlledDirectory (Join-Path $root 'private') "O:BAG:BAD:P(A;OICI;FA;;;$authoritySid)"
$publicAcl = "O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FRFX;;;$authoritySid)(A;OICI;FRFX;;;$supervisorSid)"
New-ControlledDirectory (Join-Path $root 'bin') $publicAcl
New-ControlledDirectory (Join-Path $root 'config') $publicAcl
New-ControlledDirectory (Join-Path $root 'out') "O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$authoritySid)(A;OICI;FRFX;;;$supervisorSid)"
foreach ($name in @('Initialize-AuthorityKey.ps1','Test-SupervisorIsolation.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $root "bin\$name")
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'policy-template.json') -Destination (Join-Path $root 'config\policy-template.json')
[ordered]@{authority_sid=$authoritySid;supervisor_sid=$supervisorSid;account=$accountName;root=$root;approved=$false;main_env='C:\Users\Ramy\Documents\polymarket-crypto\.env'} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'config\identity.json') -Encoding UTF8
Get-ChildItem -LiteralPath (Join-Path $root 'bin') -File | Get-FileHash -Algorithm SHA256 |
    Select-Object Hash,Path | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'config\bootstrap-manifest.json') -Encoding UTF8
Write-Output 'ACCOUNT_AND_ACLS_PREPARED; NO_KEY_YET; NO_POLICY_APPROVAL; NO_SERVICE_STARTED'
Write-Output "Authority SID: $authoritySid"
