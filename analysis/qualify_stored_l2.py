"""Qualify only existing protected L2; never load .env or private keys."""
import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.live.l2_existing_reader import load_existing, EXPECTED
from app.live.stored_l2_qualification import qualify, FLAGS


def leak_check(creds):
    needles=[v.encode() for v in creds.values()]
    paths=set()
    result=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True)
    if result.returncode:return {'verified':False,'reason':'GIT_INVENTORY_UNAVAILABLE'}
    for name in result.stdout.decode().split('\0'):
        p=Path(name)
        if name and p.suffix.lower() in ('.py','.md','.json','.log','.txt','.toml','.yaml','.yml'):paths.add(ROOT/p)
    paths.update(ROOT.glob('L2_RECOVERY_*.json'))
    for d in (ROOT/'analysis').glob('l2_*'):
        if d.is_dir():paths.update(d.glob('*.log'))
    checked=skipped=0;found=False
    for p in paths:
        try:
            if p.stat().st_size>4_000_000:skipped+=1;continue
            with p.open('rb') as h:data=h.read(4_000_001)
            found=found or any(n in data for n in needles);checked+=1
        except OSError:skipped+=1
    return {'detected':found,'files_checked':checked,'files_unchecked':skipped,
            'scope':'selected tracked working-tree text files and L2 reports/logs; excludes Git history, terminal history and inaccessible/large files',
            'global_absence_proven':False}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'INVALID_ARGUMENTS; no secrets accepted on CLI.\n')


def main():
    parser=SafeParser();parser.add_argument('--network',action='store_true');parser.add_argument('--target-machine',action='store_true');args=parser.parse_args()
    report={'phase':'AUTHENTICATED_READ_ONLY','complete':False,'ready_for_arm':False,'submit_allowed':False,
            'private_key_loaded':False,'l1_signature_produced':False,'derive_attempted':False,
            'flags':{k:os.environ.get(k,'false').strip().lower() for k in FLAGS}}
    creds=None
    try:
        if any(v!='false' for v in report['flags'].values()):raise ValueError()
        creds,report['storage']=load_existing(ROOT)
        if not creds:raise ValueError()
        report['leak_scan']=leak_check(creds)
        if report['leak_scan'].get('detected') is not False:raise ValueError()
        report['status']='STORAGE_VALIDATED_NETWORK_NOT_EXECUTED'
        if args.network:
            # User-confirmed historical wallet, classified independently by SDK pure helpers.
            from polymarket._internal.environment import PRODUCTION_CONFIG
            from polymarket._internal.wallet import classify_account,signature_type_for
            identity=classify_account(signer=EXPECTED,wallet=EXPECTED,config=PRODUCTION_CONFIG.wallet_derivation)
            config={**{k:'false' for k in FLAGS},'READONLY_SIGNER_ADDRESS':EXPECTED,'POLYMARKET_WALLET_ADDRESS':EXPECTED,
                    'READONLY_SIGNATURE_TYPE':str(signature_type_for(identity.wallet_type)),
                    'READONLY_CLOB_API_KEY':creds['apiKey'],'READONLY_CLOB_API_SECRET':creds['secret'],
                    'READONLY_CLOB_API_PASSPHRASE':creds['passphrase'], 'READONLY_EXECUTION_STATE_DB':os.environ.get('READONLY_EXECUTION_STATE_DB')}
            report['network']=asyncio.run(qualify(config))
            report['network']['execution_context']='MANUAL_TARGET_POWERSHELL' if args.target_machine else 'LOCAL_PROCESS_NETWORK_CONTEXT_REQUIRES_ATTRIBUTION'
            report['network']['provenance']['live_flags_disabled']['source']='process flags only; dotenv deliberately not read'

            report['status']='AUTHENTICATED_READ_ONLY_NOT_READY'
        report['reconciliation']={'complete':False,'status':'BLOCKED','reason':'GLOBAL_SCOPE_AND_LOCAL_LEDGER_NOT_PROVEN'}
    except BaseException:
        report['status']='BLOCKED_LOCAL_VERIFICATION_OR_QUALIFICATION'
    serialized=json.dumps(report,indent=2)
    if creds and any(v in serialized for v in creds.values()):
        serialized='{"status":"BLOCKED_REPORT_REDACTION","complete":false}'
    path=ROOT/('AUTHENTICATED_READ_ONLY_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    try:
        with path.open('x',encoding='utf-8') as handle:handle.write(serialized+'\n')
    except OSError:
        print('{"status":"REPORT_WRITE_FAILED","complete":false}')
        return 2
    print(serialized)

if __name__=='__main__':raise SystemExit(main())




