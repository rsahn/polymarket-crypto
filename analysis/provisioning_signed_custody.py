"""Candidate signed manual custody composition; never auto-accepts or trades.

Not installed in the production launch. Operator must approve the owner/key and
run this terminal outside the supervisor. Same-SID compromise is NOT isolated.
"""
import argparse
import asyncio
import ctypes
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'backend')]
from eth_account import Account
from eth_account.messages import encode_defunct
from analysis.d6.real_execution_calibration_v1.core import encoded
from analysis.d6.real_execution_calibration_v1.manual_custody import (
    ManualCustodyChannel, ManualReceiptAuthority, ManualReceiptVerifier,
    read_document, write_document, private_acl, no_links)
from app.live.l2_windows_storage import WindowsProtection, Blob

DOMAIN = 'D6_CUSTODY_RECEIPT_V1:'


def verify_signature(receipt, pinned_address):
    try:
        unsigned = dict(receipt)
        signature = unsigned.pop('custody_signature')
        return Account.recover_message(encode_defunct(text=DOMAIN+encoded(unsigned)),
            signature=bytes.fromhex(signature)).lower() == pinned_address.lower()
    except Exception:
        return False


class SignedManualChannel:
    def __init__(self, base):
        self.base = base
        self.owner, self.clock = base.owner, base.clock
        self.directory, self.sid, self.acl = base.directory, base.sid, base.acl

    def request_expired(self, request):
        return self.base.request_expired(request)

    async def accept(self, request):
        original = await self.base.accept(request)
        if original is None:
            return None
        path = self.directory/(original['receipt_id']+'.signed.json')
        if not path.exists():
            return None
        receipt = read_document(path)
        unsigned = {k:v for k,v in receipt.items() if k != 'custody_signature'}
        if unsigned != original:
            raise ValueError('SIGNED_RECEIPT_CONTENT_CHANGED')
        return receipt


class SignedReceiptAuthority:
    def __init__(self, channel, *, pinned_address):
        self.channel, self.pinned_address = channel, pinned_address
        self.manual = ManualReceiptAuthority(channel.base)

    async def verify_durable(self, receipt):
        if not verify_signature(receipt, self.pinned_address):
            return False
        unsigned = {k:v for k,v in receipt.items() if k != 'custody_signature'}
        if await self.manual.verify_durable(unsigned) is not True:
            return False
        try:
            path = self.channel.directory/(receipt['receipt_id']+'.signed.json')
            no_links(path)
            self.channel.acl(path, self.channel.sid)
            return read_document(path) == receipt
        except Exception:
            return False


def load_key(path, expected_address):
    platform = WindowsProtection()
    path = Path(path).absolute()
    no_links(path)
    path = path.resolve(strict=True)
    if any((p/'.git').exists() for p in (path.parent,*path.parents)):
        raise ValueError('KEY_MUST_BE_OUTSIDE_GIT')
    no_links(path)
    private_acl(path, platform.sid)
    with path.open('rb') as f:
        data = f.read(65537)
    if not 1 <= len(data) <= 65536:
        raise ValueError('KEY_SIZE')
    buf = (ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    incoming, outgoing = Blob(len(data), buf), Blob()
    platform.crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob),ctypes.c_void_p,
        ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
    try:
        if not platform.crypt.CryptUnprotectData(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing)):
            raise ValueError('KEY_UNAVAILABLE')
        key = Account.from_key(ctypes.string_at(outgoing.data,outgoing.size))
        if key.address.lower() != expected_address.lower():
            raise ValueError('KEY_PIN_MISMATCH')
        return key
    finally:
        if outgoing.data:
            ctypes.memset(outgoing.data,0,outgoing.size)
            platform.kernel.LocalFree(outgoing.data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--accept')
    mode.add_argument('--resume-accepted')
    parser.add_argument('--key-file', required=True)
    parser.add_argument('--approved-public-address', required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty():
        raise ValueError('OPERATOR_TTY_REQUIRED')
    key = load_key(args.key_file, args.approved_public_address)
    channel = ManualCustodyChannel(args.directory)
    # All existing challenge/ACL/context checks and human phrase remain required.
    if args.resume_accepted:
        rid = args.resume_accepted
        if not re.fullmatch('[0-9a-f]{64}',rid):
            raise ValueError('RECEIPT_ID')
        receipt = read_document(channel.directory/(rid+'.receipt.json'))
        if not asyncio.run(ManualReceiptAuthority(channel).verify_durable(receipt)):
            raise ValueError('DURABLE_ACCEPTANCE_REQUIRED')
        print(encoded(read_document(channel.directory/(rid+'.challenge.json'))))
        if input('Type SIGN ACCEPTED CUSTODY '+rid+': ') != 'SIGN ACCEPTED CUSTODY '+rid:
            raise ValueError('OPERATOR_DID_NOT_CONFIRM')
    else:
        receipt = channel.accept_interactively(args.accept)
    receipt['custody_signature'] = key.sign_message(encode_defunct(text=DOMAIN+encoded(receipt))).signature.hex()
    path = channel.directory/(receipt['receipt_id']+'.signed.json')
    if path.exists():
        stored = read_document(path)
        if {k:v for k,v in stored.items() if k!='custody_signature'} != {k:v for k,v in receipt.items() if k!='custody_signature'} or not verify_signature(stored,args.approved_public_address):
            raise ValueError('EXISTING_RECEIPT_CONFLICT')
    else:
        write_document(path, receipt)
    print('Signed custody receipt persisted. Production qualification remains separate.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('CUSTODY_BLOCKED:'+type(exc).__name__, file=sys.stderr)
        raise SystemExit(2) from None
