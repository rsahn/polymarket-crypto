"""Provision an UNAPPROVED key candidate. Never sign evidence or trust this key.
Private bytes are DPAPI CurrentUser protected outside Git with owner-only ACL.
Assigning an independent service principal and approving roles remain separate.
"""
import ctypes
import json
import os
from pathlib import Path
import sys
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys import keys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'backend')]
from app.live.l2_windows_storage import WindowsProtection, Blob
from analysis.d6.real_execution_calibration_v1.manual_custody import private_acl


def main():
    directory = Path('D:/polymarket-real-calibration/provisioning-authority-candidate')
    if directory.exists():
        raise ValueError('CANDIDATE_ALREADY_EXISTS_NO_OVERWRITE')
    if any((p/'.git').exists() for p in (directory, *directory.parents)):
        raise ValueError('OUTSIDE_GIT_REQUIRED')
    platform = WindowsProtection()
    platform.create_private_directory(directory)
    private_acl(directory, platform.sid)
    candidate = Account.create()
    encrypted = platform.protect(bytes(candidate.key))
    path = directory/'candidate.dpapi'
    with path.open('xb', buffering=0) as f:
        if f.write(encrypted) != len(encrypted):
            raise OSError('SHORT_WRITE')
        os.fsync(f.fileno())
    private_acl(path, platform.sid)
    data = path.read_bytes()
    buf = (ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    incoming, outgoing = Blob(len(data), buf), Blob()
    platform.crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    try:
        if not platform.crypt.CryptUnprotectData(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing)):
            raise ValueError('DPAPI_ROUNDTRIP_FAILED')
        restored = Account.from_key(ctypes.string_at(outgoing.data, outgoing.size))
        challenge = encode_defunct(text='D6_UNAPPROVED_KEY_STORAGE_CHECK:'+os.urandom(32).hex())
        assert Account.recover_message(challenge, signature=restored.sign_message(challenge).signature) == candidate.address
    finally:
        if outgoing.data:
            ctypes.memset(outgoing.data, 0, outgoing.size)
            platform.kernel.LocalFree(outgoing.data)
    report = {'key_id': 'candidate-local-sidecar-01', 'address': candidate.address,
        'public_key': keys.PrivateKey(bytes(candidate.key)).public_key.to_hex(),
        'storage_directory': str(directory), 'dpapi_roundtrip': True,
        'owner_only_acl_verified': True, 'approved': False, 'permitted_kinds': [],
        'independent_principal_provisioned': False,
        'limitation': 'Same Windows user as supervisor. NOT an approved authority or independent provenance.',
        'production_proofs_signed': 0}
    with (directory/'public-candidate.json').open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2);f.flush();os.fsync(f.fileno())
    with (ROOT/'analysis/provisioning_authority_candidate.json').open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
