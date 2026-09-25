"""Manual local existing-L2 recovery; preview/storage validation are offline.
Actual recovery requires a distinct interactive confirmation AFTER the preview.
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.live.l2_recovery_preparation import preview
from app.live.l2_recovery_runtime import EXPECTED, Recovery, ProtectedStore, FixedGetTransport, ExistingLocalSigner
from app.live.l2_windows_storage import WindowsProtection, storage_directory

CONFIRMATION = 'RECOVER EXISTING L2 '+EXPECTED+' POLYGON 137 NONCE 0 ONCE'


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'INVALID_ARGUMENTS: no credential or private-key arguments accepted.\n')


def validate_storage(parent):
    # Only fixed synthetic data; exclusive random sibling, never the credential directory.
    platform = WindowsProtection()
    store = ProtectedStore(parent/('PolymarketD6L2-validation-'+uuid.uuid4().hex),platform=platform)
    try:
        store.prepare()
        store.commit({'apiKey':'synthetic-validation-key','secret':'synthetic-validation-secret',
                      'passphrase':'synthetic-validation-passphrase'})
        data = store.destination.read_bytes()
        if not data or b'synthetic-validation' in data:
            raise ValueError('ENCRYPTION_VALIDATION_FAILED')
        return True
    finally:
        if store._owned:
            if store._published:
                store.destination.unlink()
                store.directory.rmdir()
            else:
                store.cleanup()


def main(argv=None):
    parser=SafeParser(description='Isolated existing-L2 recovery; default workflow is offline preview')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview',action='store_true')
    mode.add_argument('--recover-existing',action='store_true')
    parser.add_argument('--validate-storage',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    # Only public preview fields; signer is the fixed user-confirmed identity.
    public=preview(EXPECTED)
    print(json.dumps(public,indent=2))
    report={'phase':'L2_EXISTING_CREDENTIAL_RECOVERY','preview':public,'success':False,
            'stored':False,'derive_attempted':False,'signature_produced':False,
            'storage_validated':False,'real_orders_enabled':False,'live_execution_armed':False,
            'reason':'PREVIEW_ONLY'}
    output=args.output or ROOT/('L2_RECOVERY_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    try:
        if any(os.environ.get(k,'false').strip().lower()!='false' for k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')):
            raise ValueError()
        # Reserve the report BEFORE any sensitive work. No overwrite, no output path echo.
        with output.open('x',encoding='utf-8') as handle:
            try:
                directory=storage_directory(ROOT)
                if args.validate_storage:
                    report['storage_validated']=validate_storage(directory.parent)
                if args.recover_existing:
                    if not sys.stdin.isatty():
                        raise ValueError()
                    print('Separate confirmation required. Type exactly: '+CONFIRMATION)
                    if input() != CONFIRMATION:
                        raise ValueError()
                    # Only after explicit confirmation may transport/key loader be used.
                    store=ProtectedStore(directory,platform=WindowsProtection())
                    result=Recovery(FixedGetTransport(),ExistingLocalSigner(ROOT/'.env'),store).run(confirmed=True)
                    report.update(result)
                else:
                    report['success']=True
            except BaseException:
                report['reason']='LOCAL_PHASE_FAILED_NO_RETRY'
            handle.write(json.dumps(report,indent=2)+'\n')
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # Never expose raw exceptions, paths supplied via CLI, headers or responses.
        print('{"success":false,"reason":"LOCAL_PHASE_OR_REPORT_FAILED_NO_RETRY"}')
        return 2
    print(json.dumps(report,indent=2))
    return 0 if report['success'] else 2


if __name__=='__main__':
    raise SystemExit(main())
