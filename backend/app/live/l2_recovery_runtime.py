"""Isolated existing-L2 recovery. Never imported by the trading runner.
No automatic retry, credential creation, wallet bootstrap or monetary capability.
"""
import json
import os
import time
import urllib.request
from pathlib import Path

EXPECTED = '0x9348eFd557A09e644795C8F114BcF0BeF86F203a'
BASE = 'https://clob.polymarket.com'


def validate_triplet(value):
    if type(value) is not dict or set(value) != {'apiKey', 'secret', 'passphrase'}:
        raise ValueError('INVALID_CREDENTIAL_RESPONSE')
    for v in value.values():
        if type(v) is not str or not 1 <= len(v) <= 4096 or any(not 33 <= ord(c) <= 126 for c in v):
            raise ValueError('INVALID_CREDENTIAL_RESPONSE')
    return value


def _unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('AMBIGUOUS_RESPONSE')
        result[k] = v
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('REDIRECT_FORBIDDEN')


class FixedGetTransport:
    def __init__(self, *, opener=None):
        self._opener = opener or urllib.request.build_opener(NoRedirect())
        self._step = 0

    def get(self, path, headers=None):
        try:
            expected_path = ('/time', '/auth/derive-api-key')[self._step]
            if path != expected_path:
                raise ValueError()
            self._step += 1  # Consume BEFORE I/O, including failed I/O.
            if path == '/time':
                if headers:
                    raise ValueError()
            else:
                if type(headers) is not dict or set(headers) != {'POLY_ADDRESS','POLY_NONCE','POLY_TIMESTAMP','POLY_SIGNATURE'}:
                    raise ValueError()
                if headers['POLY_ADDRESS'] != EXPECTED or headers['POLY_NONCE'] != '0':
                    raise ValueError()
            request = urllib.request.Request(BASE + path, headers={
                'User-Agent':'Mozilla/5.0', 'Accept':'application/json', **(headers or {})}, method='GET')
            with self._opener.open(request, timeout=8) as response:
                if response.status != 200:
                    raise ValueError()
                raw = response.read(16385)
                if len(raw) > 16384:
                    raise ValueError()
                return json.loads(raw, object_pairs_hook=_unique_object)
        except BaseException:
            self._step = 2
            raise ValueError('RECOVERY_GET_FAILED') from None


class ProtectedStore:
    def __init__(self, directory, *, platform):
        self.directory = Path(directory)
        self.destination = self.directory / 'credential.dpapi'
        self.temporary = self.directory / '.credential.dpapi.tmp'
        self.platform = platform
        self._owned = False
        self._published = False

    def prepare(self):
        # A pre-existing directory is blocked, even if empty. Never reuse a stale attempt.
        self.platform.create_private_directory(self.directory)
        self._owned = True

    def _write_ciphertext(self, data):
        with self.temporary.open('xb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def commit(self, triplet):
        if not self._owned or self._published:
            raise ValueError('STORAGE_NOT_READY')
        plaintext = json.dumps({'version':1,'environment':'production','chain_id':137,
            'nonce':0,'signer':EXPECTED,'credentials':validate_triplet(triplet)}, separators=(',', ':')).encode()
        try:
            ciphertext = self.platform.protect(plaintext)
        finally:
            del plaintext
        self._write_ciphertext(ciphertext)
        self.platform.publish(self.temporary, self.destination)
        self._published = True

    def cleanup(self):
        if self._owned and not self._published:
            # Only paths belonging to the directory this instance created are touched.
            self.temporary.unlink(missing_ok=True)
            self.directory.rmdir()
            self._owned = False


class Recovery:
    def __init__(self, transport, signer_source, store, *, signer=EXPECTED, nonce=0,
                 chain_id=137, environment='production'):
        if signer != EXPECTED or type(nonce) is not int or nonce != 0 or type(chain_id) is not int or chain_id != 137 or environment != 'production':
            raise ValueError('FIXED_RECOVERY_IDENTITY_REQUIRED')
        self.transport, self.signer, self.store = transport, signer_source, store
        self._spent = False

    def run(self, *, confirmed=False):
        report = {'success':False,'stored':False,'derive_attempted':False,'signature_produced':False,
                  'real_orders_enabled':False,'live_execution_armed':False,'reason':'BLOCKED'}
        if self._spent:
            report['reason'] = 'ATTEMPT_ALREADY_SPENT'
            return report
        self._spent = True
        try:
            if confirmed is not True:
                raise ValueError()
            if any(os.environ.get(k,'false').strip().lower() != 'false' for k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')):
                raise ValueError()
            self.store.prepare()
            stamp = self.transport.get('/time')
            if type(stamp) is not int or abs(stamp - int(time.time())) > 5:
                raise ValueError()
            headers = self.signer.headers(stamp)
            report['signature_produced'] = True
            # Signer providers must bind all L1 fields; no other address/nonce allowed.
            if headers.get('POLY_ADDRESS') != EXPECTED or headers.get('POLY_NONCE') != '0' or headers.get('POLY_TIMESTAMP') != str(stamp):
                raise ValueError()
            report['derive_attempted'] = True
            payload = self.transport.get('/auth/derive-api-key', headers)
            self.store.commit(validate_triplet(payload))
            report.update(success=True, stored=True, reason='EXISTING_CREDENTIAL_STORED')
        except BaseException:
            # Never render exception text, response, headers, key or traceback.
            report['reason'] = 'RECOVERY_FAILED_NO_RETRY'
        finally:
            try:
                self.store.cleanup()
            except BaseException:
                report['reason'] = 'STORAGE_CLEANUP_REQUIRED'
        return report


class ExistingLocalSigner:
    """Key read is delayed until headers(), after preview, confirmation and time GET."""
    def __init__(self, env_path):
        self._env_path = Path(env_path)

    def headers(self, stamp):
        try:
            from importlib.metadata import version
            if version('polymarket-client') != '0.11.0':
                raise ValueError()
            from eth_account import Account
            from polymarket._internal.l1_auth import build_api_key_auth_typed_data
            key = None
            flags = {}
            with self._env_path.open(encoding='utf-8-sig') as handle:
                for line in handle:
                    name, sep, value = line.partition('=')
                    name = name.strip()
                    if sep and name in ('SIGNER_PRIVATE_KEY','REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED'):
                        if name in flags:
                            raise ValueError()
                        flags[name] = True
                        value = value.strip().strip('\"\'')
                        if name == 'SIGNER_PRIVATE_KEY':
                            key = value
                        elif value.lower() != 'false':
                            raise ValueError()
            if not key:
                raise ValueError()
            account = Account.from_key(key)
            del key
            if account.address.lower() != EXPECTED.lower():
                raise ValueError()
            typed = build_api_key_auth_typed_data(address=EXPECTED,chain_id=137,timestamp=stamp,nonce=0)
            signed = account.sign_typed_data(full_message=typed)
            return {'POLY_ADDRESS':EXPECTED,'POLY_NONCE':'0','POLY_TIMESTAMP':str(stamp),
                    'POLY_SIGNATURE':'0x'+signed.signature.hex()}
        except BaseException:
            raise ValueError('LOCAL_SIGNER_REJECTED') from None
