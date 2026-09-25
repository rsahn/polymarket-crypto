"""Manual D6 scoped genesis. No trading, credential recovery, or collateral requalification."""
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.live.genesis_ledger import expected_wallet,create_genesis,read_genesis,digest,LIMITS
from app.live.genesis_discovery import conditional_snapshot
from app.live.genesis_readonly import read_local_ledger
from app.live.collateral_onchain import PublicRPC,CONTRACT
from app.live.deposit_qualification import FLAGS,CLOB,DATA,write_report
from app.live.network_readonly import GetOnlyTransport,ReadOnlyClient
from app.live.production_readonly import drain,plain,BookStateSource,GeoBlockSource,SessionRiskSource
from app.live.readiness import ProductionReadinessCheck
from app.live.l2_existing_reader import load_existing,EXPECTED

LEDGER=ROOT/'runtime'/'d6_genesis.db'

class RecoveryDetected(Exception):pass

class Observed:
    def __init__(self,value):self.value=value
    def read(self):return self.value


def qualification():
    paths=sorted(ROOT.glob('COLLATERAL_INVENTORY_READ_ONLY_*.json'),reverse=True)
    for p in paths:
        value=json.loads(p.read_text(encoding='utf-8'))
        c=value.get('collateral',{})
        if c.get('contract')==CONTRACT and c.get('chain_id')==137 and c.get('symbol')=='pUSD' and c.get('decimals')==6 and c.get('account_binding_verified') is True:
            return value,hashlib.sha256(p.read_bytes()).hexdigest()
    raise ValueError('QUALIFIED_COLLATERAL_REPORT_MISSING')


async def run(network=False):
    old,qualification_hash=qualification();wallet=expected_wallet();creds=None;audit=[]
    c=old['collateral'];old_views=old['inventory']['remote_views']
    account={'available':True,'authenticated':True,'observed_ms':c['observed_ms'],
        'balance_collateral':c['balance_human'],'collateral_symbol':'pUSD','complete':False,
        'reason':'PRIOR_OBSERVATION_REQUIRES_FRESH_ACCOUNT_READ'}
    positions={'available':True,'observed_ms':old_views['positions']['observed_ms'],'complete':False,
        'reason':'INDEX_VIEW_ONLY_NO_CONDITIONAL_DISCOVERY'}
    local=lambda:read_genesis(LEDGER) if LEDGER.exists() else None
    risk=SessionRiskSource(lambda:None)
    geo=Observed({'available':False,'reason':'NO_FRESH_GEOBLOCK_IN_OFFLINE_MODE'})
    decision={'created':False,'phase':'GENESIS_PENDING','reasons':['FRESH_CTF_DISCOVERY_AND_BRACKETED_ACCOUNT_SNAPSHOT_REQUIRED']}
    rpc=None
    if network:
        try:
            from importlib.metadata import version
            from polymarket._internal.environment import PRODUCTION_CONFIG as env
            from polymarket._internal.hmac import build_hmac_signature
            if version('polymarket-client')!='0.11.0':raise ValueError()
            stamp=await GetOnlyTransport(CLOB,('/time',),audit=audit).get_json('/time')
            if type(stamp) is not int or abs(time.time()-stamp)>5:raise ValueError()
            rpc=PublicRPC(wallet)
            old_local,known=read_local_ledger(os.getenv('READONLY_EXECUTION_STATE_DB'))
            if old_local.get('recovery_pending'):raise RecoveryDetected()
            if old_local.get('configured'):raise ValueError('EXISTING_LEDGER_REQUIRES_EXPLICIT_IMPORT')
            discovered=await asyncio.to_thread(conditional_snapshot,rpc,known)
            if any(int(v)>0 for v in discovered['balances'].values()):raise RecoveryDetected()
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
            async def views():
                started=int(time.time()*1000)
                values=await asyncio.gather(drain(client.list_positions(user=wallet,full_history=True,include_archived=True,filter_type='TOKENS',filter_amount=0)),
                    drain(client.list_open_orders()),drain(client.list_account_trades()))
                return dict(zip(('positions','orders','trades'),values)),started
            first,first_ms=await views();second,second_ms=await views()
            if any(first.values()) or any(second.values()):raise RecoveryDetected()
            balance_ms=int(time.time()*1000)
            bal=plain(await client.get_balance_allowance(asset_type='COLLATERAL'))
            raw=str(bal['balance'])
            if not raw.isdigit():raise ValueError()
            allowances=[str(v) for k,v in bal['allowances'].items() if k.lower()==env.standard_exchange.lower()]
            if len(allowances)!=1 or not allowances[0].isdigit():raise ValueError()
            now=int(time.time()*1000)
            end=discovered['to_block'];block_hash=rpc.call('eth_getBlockByNumber',[hex(end),False])['hash']
            if not 0<=now-discovered['block_timestamp']*1000<=120000:raise ValueError('CTF_ANCHOR_STALE')
            snapshot={'chain_id':137,'wallet':wallet,'block_number':end,'block_hash':discovered['block_hash'],
                'timestamp_ms':now,'block_hash_rechecked':block_hash==discovered['block_hash'],
                'dedicated_wallet_policy':'D6_DEDICATED_FROM_GENESIS','local_prior_state':'NO_AUTHORITATIVE_LEDGER_CONFIGURED',
                'collateral':{'contract':CONTRACT,'balance_raw':raw,'qualification_sha256':qualification_hash},
                'views':{n:{'rows':first[n],'pagination_complete':True,'observed_ms':first_ms,'repeat_sha256':digest(second[n])} for n in first},
                'conditional_assets':discovered,'journal_assets':sorted(known),'coverage_limitations':LIMITS}
            decision=create_genesis(LEDGER,snapshot)
            account={'available':True,'authenticated':True,'observed_ms':min(second_ms,balance_ms),'collateral_symbol':'pUSD',
                'balance_collateral':str(Decimal(raw)/1000000),'allowance_collateral':str(Decimal(allowances[0])/1000000),
                'open_order_ids':[r['id'] for r in second['orders']],
                'complete':decision.get('created') is True,'scope':'D6_SCOPED_GENESIS_NOT_GLOBAL_HISTORY'}
            positions={'available':True,'observed_ms':min(second_ms,discovered['block_timestamp']*1000),'balances':discovered['balances'],
                'complete':decision.get('created') is True,'scope':'CTF_AND_INDEXER_AT_GENESIS'}
            if decision.get('created'):
                verified=read_genesis(LEDGER);verified['reconciled_now']=True
                local=lambda:verified
                risk=Observed({'available':True,'observed_ms':now,'allow':Decimal(raw)/1000000>=25,
                    'session_pnl':'0','open_positions':0,'source':'NEW_SESSION_START_FROM_VERIFIED_EMPTY_GENESIS',
                    'prior_history_pnl_not_claimed':True})
        except RecoveryDetected:
            decision={'created':False,'phase':'RECOVERY_REQUIRED','reasons':['UNEXPLAINED_ORDER_POSITION_TRADE_OR_LOCAL_RECOVERY']}
        except Exception:
            decision={'created':False,'phase':'GENESIS_PENDING','reasons':['DISCOVERY_OR_FRESH_ACCOUNT_EVIDENCE_UNAVAILABLE_NO_FALLBACK']}
        geo=GeoBlockSource(fetch=lambda:GetOnlyTransport('https://polymarket.com',('/api/geoblock',),audit=audit).get_json('/api/geoblock'))
    readiness=await ProductionReadinessCheck(account=Observed(account),positions=Observed(positions),
        book=BookStateSource(),geo=geo,risk=risk,local_reader=local,collateral_unit='pUSD').run()
    # Detailed order IDs and snapshot live only in the local ignored ledger.
    readiness['observations']['account'].pop('open_order_ids',None)
    readiness['observations']['positions'].pop('balances',None)
    report={'phase':'D6_GENESIS_AND_FULL_READINESS','genesis':decision,'readiness':readiness,
        'network_executed':network,'get_requests':audit,'rpc_calls':rpc.calls if rpc else [],
        'prior_history_globally_known':False,'coverage_limitations':LIMITS,
        'book_source':'ACTUAL_ADAPTER_DISCONNECTED_NO_PRODUCTION_STREAM',
        'future_execution_binding_ready':False,
        'execution_binding_reason':'RUNNER_REMAINS_DISCONNECTED_MUST_JOURNAL_BEFORE_ANY_FUTURE_UNLOCK',
        'ledger_path':'runtime/d6_genesis.db','private_key_loaded':False,'l1_signature_produced':False}
    if creds and any(v in json.dumps(report) for v in creds.values()):raise ValueError()
    return report


def main():
    if sys.argv[1:] not in (['--offline'],['--target-machine']):print('Use --offline or --target-machine.');return 2
    try:
        if any(os.getenv(k,'false').strip().lower()!='false' for k in FLAGS):raise ValueError()
        report=asyncio.run(run(sys.argv[1]=='--target-machine'))
    except BaseException:report={'phase':'D6_GENESIS_AND_FULL_READINESS','status':'BLOCKED','ready_for_arm':False}
    p=ROOT/('GENESIS_READINESS_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    write_report(p,report);print(json.dumps(report,indent=2));print('REPORT_FILE='+p.name)

if __name__=='__main__':raise SystemExit(main())
