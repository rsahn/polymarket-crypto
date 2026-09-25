"""Manual target-machine GET-only Deposit Wallet qualification; no dotenv."""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.live.deposit_qualification import qualify_deposit,write_report,FLAGS
from app.live.l2_existing_reader import load_existing


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-machine',action='store_true',required=True)
    parser.parse_args()
    flags={k:os.environ.get(k,'false').strip().lower() for k in FLAGS}
    report={'phase':'DEPOSIT_WALLET_READ_ONLY','complete':False,'status':'BLOCKED_LIVE_FLAGS'}
    try:
        if all(v=='false' for v in flags.values()):
            report=asyncio.run(qualify_deposit(lambda:load_existing(ROOT)))
    except BaseException:
        report={'phase':'DEPOSIT_WALLET_READ_ONLY','complete':False,'status':'BLOCKED_INTERRUPTED_OR_INTERNAL'}
    report['flags']=flags
    report['execution_context']='MANUAL_TARGET_POWERSHELL'
    path=ROOT/('DEPOSIT_WALLET_READ_ONLY_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    try:write_report(path,report)
    except OSError:
        print('{"status":"REPORT_WRITE_FAILED","complete":false}');return 2
    print(json.dumps(report,indent=2))
    print('REPORT_FILE='+path.name)


if __name__=='__main__':raise SystemExit(main())
