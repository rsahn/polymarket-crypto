"""One public diagnostic request; never discovers inventory or creates genesis."""
import json
import os
import re
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.live.collateral_onchain import PublicRPC,CTF,validate_rpc_endpoint
from app.live.genesis_ledger import expected_wallet
from app.live.deposit_qualification import write_report


def run():
    flags={k:os.getenv(k,'false').strip().lower() for k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')}
    report={'phase':'POLYGON_ARCHIVE_RPC_QUALIFICATION','status':'BLOCKED','rpc':'CONFIGURED_POLYGON_ARCHIVE_RPC_URL',
            'from_block':94331195,'to_block':94331204,'rpc_calls':[],
            'flags':flags,'credentials_loaded':False,'private_key_loaded':False,
            'authenticated_get_attempts':0,'genesis_created':False,'ready_for_arm':False}
    if any(v!='false' for v in flags.values()):return report
    endpoint=os.getenv('POLYGON_ARCHIVE_RPC_URL')
    report['rpc_configuration_source']='PROCESS_ENVIRONMENT_ONLY_NO_DOTENV'
    if endpoint is None or not endpoint.strip():
        report['reason']='POLYGON_ARCHIVE_RPC_URL_NOT_CONFIGURED';return report
    try:validate_rpc_endpoint(endpoint)
    except ValueError:
        report['reason']='POLYGON_ARCHIVE_RPC_URL_INVALID';return report
    rpc=None
    try:
        from eth_utils import keccak
        wallet=expected_wallet();rpc=PublicRPC(wallet,endpoint=endpoint)
        if rpc.call('eth_chainId',[])!='0x89':
            report['reason']='CHAIN_MISMATCH';return report
        report['chain_id']=137
        code=rpc.call('eth_getCode',[CTF,hex(94331195)])
        if not isinstance(code,str) or not re.fullmatch('0x(?:[0-9a-fA-F]{2})+',code) or int(code[2:],16)==0:
            report['reason']='HISTORICAL_CTF_CODE_UNAVAILABLE';return report
        report['historical_code_present']=True
        report['historical_block']=94331195
        signatures=['0x'+keccak(text=x).hex() for x in ('TransferSingle(address,address,address,uint256,uint256)','TransferBatch(address,address,address,uint256[],uint256[])')]
        rows=rpc.call('eth_getLogs',[{'address':CTF,'fromBlock':hex(94331195),'toBlock':hex(94331204),
                       'topics':[signatures,None,None,'0x'+wallet[2:].lower().rjust(64,'0')]}])
        if not isinstance(rows,list):report['reason']='RESULT_NOT_LIST'
        else:
            report.update(status='PASS_READ_ONLY_RPC',historical_logs_readable=True,rows_count=len(rows),
                          reason='TESTED_BLOCK_AND_TEN_BLOCK_RANGE_ONLY_NO_GLOBAL_ARCHIVE_OR_GENESIS_CLAIM')
    except Exception:report['reason']='PUBLIC_READ_FAILED_SEE_SANITIZED_RPC_CALLS'
    finally:
        if rpc is not None:report['rpc_calls']=rpc.calls
    return report


def main():
    if sys.argv[1:]!=['--target-machine']:return 2
    report=run()
    path=ROOT/('CTF_RPC_DIAGNOSTIC_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    write_report(path,report)
    print(json.dumps(report,indent=2));print('REPORT_FILE='+path.name)

if __name__=='__main__':raise SystemExit(main())
