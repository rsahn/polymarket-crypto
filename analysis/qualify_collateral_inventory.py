"""Manual collateral RPC + inventory GET qualification. No dotenv or private key."""
import asyncio
import json
import os
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.live.l2_existing_reader import load_existing,EXPECTED
from app.live.network_readonly import GetOnlyTransport,ReadOnlyClient
from app.live.deposit_qualification import write_report,FLAGS,CLOB,DATA
from app.live.collateral_onchain import PublicRPC,qualify_collateral,bind_collateral
from app.live.genesis_readonly import read_local_ledger,initial_inventory
from app.live.production_readonly import drain,plain,number
from app.live.readiness import ProductionReadinessCheck


async def run():
    import time
    from importlib.metadata import version
    if version('polymarket-client')!='0.11.0':raise ValueError()
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    from polymarket._internal.wallet import derive_beacon_deposit_wallet_address
    from polymarket._internal.hmac import build_hmac_signature
    wallet=derive_beacon_deposit_wallet_address(EXPECTED,env.wallet_derivation)
    rpc=PublicRPC(wallet);audit=[];views={};creds=None
    collateral={'conversion_allowed':False,'status':'NOT_MEASURED'}
    local,assets=read_local_ledger(os.getenv('READONLY_EXECUTION_STATE_DB'))
    try:
        stamp=await GetOnlyTransport(CLOB,('/time',),audit=audit).get_json('/time')
        if type(stamp) is not int or abs(time.time()-stamp)>5:raise ValueError()
        creds,storage=load_existing(ROOT)
        if not creds or storage.get('storage_validated') is not True:raise ValueError()
        async def headers(path):
            if path not in ('/balance-allowance','/data/orders','/data/trades'):raise ValueError()
            t=int(time.time())
            return {'POLY_ADDRESS':EXPECTED,'POLY_API_KEY':creds['apiKey'],'POLY_PASSPHRASE':creds['passphrase'],
                    'POLY_TIMESTAMP':str(t),'POLY_SIGNATURE':build_hmac_signature(secret=creds['secret'],timestamp=t,method='GET',path=path,body=None)}
        client=ReadOnlyClient(wallet=wallet,signature_type=3,
            clob=GetOnlyTransport(CLOB,('/balance-allowance','/data/orders','/data/trades'),headers=headers,audit=audit),
            data=GetOnlyTransport(DATA,('/v2/positions',),audit=audit))
        before=plain(await client.get_balance_allowance(asset_type='COLLATERAL'))['balance']
        collateral=await asyncio.to_thread(qualify_collateral,rpc)
        after=plain(await client.get_balance_allowance(asset_type='COLLATERAL'))['balance']
        collateral=bind_collateral(collateral,str(before),str(after))
        sources={'positions':lambda:client.list_positions(user=wallet,full_history=True,include_archived=True,filter_type='TOKENS',filter_amount=0),
                 'orders':client.list_open_orders,'trades':client.list_account_trades}
        for name,source in sources.items():
            try:
                rows=await drain(source())
                for row in rows:
                    if name=='positions' and (str(row.get('wallet','')).lower()!=wallet.lower() or number(row['current_size'])<0):raise ValueError()
                views[name]={'status':'PASS','count':len(rows),'pagination_complete':True,'complete':False,
                    'scope':'INDEX_CURRENT_FILTER' if name=='positions' else 'CREDENTIAL_VIEW',
                    'observed_ms':int(time.time()*1000)}
            except Exception:views[name]={'status':'BLOCKED','complete':False}
    except Exception:views['account_reads']={'status':'BLOCKED','reason':'PREFLIGHT_STORAGE_OR_AUTH_READ_FAILED_NO_FALLBACK'}
    inventory=initial_inventory(views,local)
    report={'phase':'COLLATERAL_INVENTORY_READ_ONLY','collateral':collateral,'inventory':inventory,
            'rpc_calls':rpc.calls,'get_requests':audit,'private_key_loaded':False,'l1_signature_produced':False,
            'readiness':ProductionReadinessCheck.qualification_snapshot(collateral,inventory,provenance={'wallet':'USER_CONFIRMED_BEACON_AND_PUBLIC_CREATE2','collateral':'CURRENT_RPC_AND_TYPE3_GETS','inventory':'PAGINATED_GETS_AND_READ_ONLY_SQLITE'})}
    if creds and any(v in json.dumps(report) for v in creds.values()):raise ValueError()
    return report


def main():
    if sys.argv[1:]!=['--target-machine']:
        print('Use --target-machine only.');return 2
    try:
        if any(os.getenv(k,'false').strip().lower()!='false' for k in FLAGS):raise ValueError()
        report=asyncio.run(run())
    except BaseException:report={'status':'BLOCKED','ready_for_arm':False,'submit_allowed':False}
    p=ROOT/('COLLATERAL_INVENTORY_READ_ONLY_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    try:write_report(p,report)
    except OSError:print('REPORT_WRITE_FAILED');return 2
    print(json.dumps(report,indent=2));print('REPORT_FILE='+p.name)

if __name__=='__main__':raise SystemExit(main())
