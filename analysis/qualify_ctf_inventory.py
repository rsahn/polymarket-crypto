"""Separate bounded CTF read-only probe: explicit block range, no credentials."""
import argparse
import json
import os
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.live.collateral_onchain import PublicRPC
from app.live.ctf_inventory_probe import scan_ctf
from app.live.genesis_readonly import read_local_ledger
from app.live.l2_existing_reader import EXPECTED
from app.live.deposit_qualification import FLAGS,write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-block',type=int,required=True);parser.add_argument('--to-block',type=int,required=True)
    args=parser.parse_args()
    report={'status':'BLOCKED','complete':False}
    try:
        if any(os.getenv(k,'false').strip().lower()!='false' for k in FLAGS):raise ValueError()
        from importlib.metadata import version
        if version('polymarket-client')!='0.11.0':raise ValueError()
        from polymarket._internal.environment import PRODUCTION_CONFIG as env
        from polymarket._internal.wallet import derive_beacon_deposit_wallet_address
        wallet=derive_beacon_deposit_wallet_address(EXPECTED,env.wallet_derivation)
        local,known=read_local_ledger(os.getenv('READONLY_EXECUTION_STATE_DB'))
        rpc=PublicRPC(wallet);report=scan_ctf(rpc,args.from_block,args.to_block,known)
        report['local_ledger']=local;report['rpc_calls']=rpc.calls
    except BaseException:pass
    path=ROOT/('CTF_INVENTORY_READ_ONLY_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    try:write_report(path,report)
    except OSError:print('REPORT_WRITE_FAILED');return 2
    print(json.dumps(report,indent=2));print('REPORT_FILE='+path.name)

if __name__=='__main__':raise SystemExit(main())
