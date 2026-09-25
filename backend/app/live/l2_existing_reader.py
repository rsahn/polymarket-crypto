"""Existing DPAPI L2 reader: no private-key, signing or recovery entry point."""
import ctypes
import json
import subprocess
from pathlib import Path
from .l2_windows_storage import WindowsProtection, Blob, storage_directory

EXPECTED='0x9348eFd557A09e644795C8F114BcF0BeF86F203a'


def validate_envelope(value):
    if type(value) is not dict or set(value)!={'version','environment','chain_id','nonce','signer','credentials'}:
        raise ValueError('INVALID_ENVELOPE')
    for k,n in [('version',1),('chain_id',137),('nonce',0)]:
        if type(value[k]) is not int or value[k]!=n:raise ValueError('INVALID_BINDING')
    if value['signer']!=EXPECTED or value['environment']!='production':raise ValueError('INVALID_BINDING')
    creds=value['credentials']
    if type(creds) is not dict or set(creds)!={'apiKey','secret','passphrase'}:raise ValueError('INVALID_TRIPLET')
    if any(type(v) is not str or not 1<=len(v)<=4096 or any(not 33<=ord(c)<=126 for c in v) for v in creds.values()):raise ValueError('INVALID_TRIPLET')
    return creds


def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('DUPLICATE_JSON')
        result[k]=v
    return result


def verify_acl(directory, sid):
    # Only paths are passed to .NET; file contents and credentials never leave this process.
    command='''$ErrorActionPreference='Stop'; $p=([Console]::In.ReadToEnd() | ConvertFrom-Json); $d=[System.IO.Directory]::GetAccessControl($p); $f=[System.IO.File]::GetAccessControl([System.IO.Path]::Combine($p,'credential.dpapi')); @{protected=$d.AreAccessRulesProtected; rules=@($d.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object { @{sid=$_.IdentityReference.Value; type=$_.AccessControlType.ToString(); rights=[int]$_.FileSystemRights} }); file_rules=@($f.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object { @{sid=$_.IdentityReference.Value; type=$_.AccessControlType.ToString(); rights=[int]$_.FileSystemRights} })} | ConvertTo-Json -Depth 4'''
    r=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],input=json.dumps(str(directory)),capture_output=True,text=True,timeout=15)
    if r.returncode:raise ValueError('ACL_UNAVAILABLE')
    acl=json.loads(r.stdout)
    if acl['protected'] is not True:raise ValueError('ACL_UNPROTECTED')
    for key in ('rules','file_rules'):
        rows=acl[key]
        if len(rows)!=1 or rows[0]['sid']!=sid or rows[0]['type']!='Allow' or rows[0]['rights']!=2032127:raise ValueError('ACL_UNEXPECTED')


def load_existing(repository):
    report={'file_present':False,'permissions_verified':False,'dpapi_decrypted':False,'triplet_complete':False,'binding_verified':False,'storage_validated':False}
    creds=None
    try:
        directory=storage_directory(repository);path=directory/'credential.dpapi'
        report['file_present']=path.is_file()
        if not report['file_present']:raise ValueError()
        for p in (path,directory,*directory.parents):
            if p.is_symlink() or p.is_junction():raise ValueError()
        platform=WindowsProtection();verify_acl(directory,platform.sid)
        report['permissions_verified']=True
        with path.open('rb') as handle:data=handle.read(65537)
        if not 1<=len(data)<=65536:raise ValueError()
        buffer=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
        incoming=Blob(len(data),buffer);outgoing=Blob()
        platform.crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
        try:
            if not platform.crypt.CryptUnprotectData(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing)):raise ValueError()
            report['dpapi_decrypted']=True
            value=json.loads(ctypes.string_at(outgoing.data,outgoing.size),object_pairs_hook=unique)
            creds=validate_envelope(value)
            report.update(triplet_complete=True,binding_verified=True,storage_validated=True)
        finally:
            if outgoing.data:
                ctypes.memset(outgoing.data,0,outgoing.size)
                platform.kernel.LocalFree(outgoing.data)
    except BaseException:
        creds=None;report['reason']='LOCAL_STORAGE_VERIFICATION_FAILED'
    return creds,report
