"""Manual read-only readiness from an existing genesis. Never creates a genesis."""
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'backend'))
from app.live.genesis_ledger import read_genesis,append_activity,expected_wallet,LIMITS
from app.live.forward_readiness import evaluate_baseline,ObservationSource,ForwardSessionRiskSource,validate_generation
from app.live.readonly_book_stream import StreamBook
from app.live.production_readonly import now_ms,drain,plain,units,GeoBlockSource,BookStateSource
from app.live.readiness import ProductionReadinessCheck
from app.live.network_readonly import GetOnlyTransport,ReadOnlyClient
from app.live.collateral_onchain import PublicRPC,validate_rpc_endpoint,CONTRACT
from app.live.ctf_inventory_probe import scan_ctf
from app.live.deposit_qualification import CLOB,DATA,FLAGS,write_report
from app.live.l2_existing_reader import load_existing,EXPECTED

LEDGER=ROOT/'runtime'/'d6_genesis.db'


def incremental_inventory(rpc,prior):
    s=prior['snapshot']
    if rpc.call('eth_chainId',[])!='0x89':raise ValueError('CHAIN')
    anchor=rpc.call('eth_getBlockByNumber',[hex(s['block_number']),False])
    if anchor['hash']!=s['block_hash']:raise ValueError('GENESIS_ANCHOR_CHANGED')
    head=rpc.call('eth_getBlockByNumber',['latest',False]);end=int(head['number'],16)
    start=s['block_number']+1
    # Never re-read genesis events, and never silently truncate a large gap.
    if end<start or end-start>=50000:raise ValueError('INCREMENTAL_RANGE_UNAVAILABLE')
    captured={};started=now_ms()
    result=scan_ctf(rpc,start,end,set(s['conditional_assets']['balances']),capture=captured)
    if result['status']!='PASS_SCOPED_READS' or result['block_hash']!=head['hash']:raise ValueError('INCREMENTAL_SCAN_FAILED')
    return {**result,'balances':captured['balances'],'observed_ms':min(started,int(head['timestamp'],16)*1000),
            'provenance':'POST_GENESIS_CTF_INCOMING_EVENTS_AND_ANCHORED_BALANCES'}


def advance_inventory(rpc,prior,previous):
    """Continue at the already verified cursor; never rescan the baseline."""
    anchor=rpc.call('eth_getBlockByNumber',[hex(prior['snapshot']['block_number']),False])
    if anchor['hash']!=prior['snapshot']['block_hash']:raise ValueError('GENESIS_ANCHOR_CHANGED')
    current=rpc.call('eth_getBlockByNumber',['latest',False])
    if int(current['number'],16)==previous['to_block']:
        if current['hash']!=previous['block_hash']:raise ValueError('CURSOR_REORG')
        return previous
    virtual={'snapshot':{**prior['snapshot'],'block_number':previous['to_block'],'block_hash':previous['block_hash'],
                        'conditional_assets':{'balances':previous['balances']}}}
    result=incremental_inventory(rpc,virtual)
    result['from_block']=previous['from_block']
    result['events_count']+=previous['events_count']
    return result


async def discover_book(audit):
    from app.collectors.polymarket import PolymarketMarketDiscovery
    from app.d5.identity import MarketIdentity
    from analysis.d6.paper_live import V1
    if V1['market']!='5m':raise ValueError('UNREVIEWED_V1_MARKET')
    start=int(time.time())//300*300;slug=f'btc-updown-5m-{start}'
    path='/markets/slug/'+slug
    value=await GetOnlyTransport('https://gamma-api.polymarket.com',(path,),audit=audit).get_json(path)
    market=PolymarketMarketDiscovery.parse_market_list([value])
    if len(market)!=1:raise ValueError('DISCOVERY_AMBIGUOUS')
    ident=MarketIdentity.from_market(market[0])
    if ident.market_slug!=slug or ident.expiry_ts_ms!=(start+300)*1000 or value.get('closed') is not False or value.get('active') is not True:
        raise ValueError('MARKET_NOT_CURRENT')
    return StreamBook(slug,ident.condition_id,(ident.token_up,ident.token_down),ident.expiry_ts_ms)


async def fresh_views(client):
    async def observed(coro):
        started=now_ms();value=await coro
        return value,started
    values=await asyncio.gather(
        observed(client.get_balance_allowance(asset_type='COLLATERAL')),
        observed(drain(client.list_open_orders())),observed(drain(client.list_account_trades())),
        observed(drain(client.list_positions(user=client.wallet,full_history=True,include_archived=True,filter_type='TOKENS',filter_amount=0))))
    return dict(zip(('balance','orders','trades','positions'),values))


def witness_inventory(rpc,inventory):
    """A NEW remote observation, not a refresh of the cached scan.
    Same canonical latest head proves its scanned CTF state is still current.
    Does not cover pending transactions or credential-global off-chain activity.
    """
    started=now_ms()
    head=rpc.call('eth_getBlockByNumber',['latest',False])
    number=int(head['number'],16)
    if number<inventory['to_block']:raise ValueError('HEAD_REGRESSION')
    if number>inventory['to_block']:raise ValueError('HEAD_ADVANCED')
    if head['hash']!=inventory['block_hash']:raise ValueError('CURSOR_REORG')
    block_time=int(head['timestamp'],16)*1000
    if block_time>started:raise ValueError('FUTURE_BLOCK')
    return {**inventory,'scan_observed_ms':inventory.get('scan_observed_ms',inventory['observed_ms']),
            'observed_ms':started,'head_witness_started_ms':started,'head_witness_finished_ms':now_ms(),
            'head_block_timestamp_ms':block_time,'head_unchanged_verified':True,
            'provenance':'NEW_LATEST_HEAD_READ_MATCHES_COMPLETE_SCANNED_CTF_WATERMARK'}


async def acquire_final_views(client,geo_reader,rpc,prior,inventory):
    # Catch-up is preparation. The final remote head witness runs alongside GETs.
    geoval=await geo_reader.read()
    for attempt in range(1,4):
        inventory=await asyncio.to_thread(advance_inventory,rpc,prior,inventory)
        results=await asyncio.gather(fresh_views(client),asyncio.to_thread(witness_inventory,rpc,inventory),return_exceptions=True)
        observed,witness=results
        if isinstance(observed,BaseException):raise ValueError('ACCOUNT_GENERATION_FAILED') from None
        if isinstance(witness,ValueError) and witness.args==('HEAD_ADVANCED',):continue
        if isinstance(witness,BaseException):raise ValueError('INVENTORY_WITNESS_FAILED') from None
        return observed,geoval,{**witness,'generation_attempt':attempt}
    raise ValueError('HEAD_ADVANCED_GENERATION_RETRY_LIMIT')


def inventory_metadata(inventory):
    return {k:inventory[k] for k in ('from_block','to_block','block_hash','events_count','assets_checked','observed_ms','provenance',
        'scan_observed_ms','head_witness_started_ms','head_witness_finished_ms','head_block_timestamp_ms',
        'head_unchanged_verified','generation_attempt') if k in inventory}


def annotate(readiness):
    source_for={'wallet_auth':'account','balance_pusd':'account','allowance_pusd':'account','open_orders':'account',
        'inventory':'positions','account_reconciliation':'positions','session_risk':'risk','book_freshness':'book','geoblock':'geo'}
    at=readiness['evaluated_ms'];details={}
    for name,passed in readiness['checks'].items():
        source=source_for.get(name,'local');o=readiness['observations'].get(source,{})
        details[name]={'status':'PASS' if passed else 'BLOCKED','source':o.get('provenance',o.get('source',source)),
            'observed_ms':o.get('observed_ms'),'evaluated_ms':at,
            'reason':'INVARIANT_SATISFIED' if passed else o.get('reason') or 'MISSING_STALE_OR_UNRECONCILED',
            'freshness_limit_ms':60000 if name=='geoblock' else 500 if source!='local' else None}
    readiness['check_details']=details
    for obs in readiness['observations'].values():
        for key in ('wallet','open_order_ids','balances','books'):obs.pop(key,None)
    return readiness


async def run(target=False):
    audit=[];rpc=None;creds=None;task=None;prior=None
    account=ObservationSource({'available':False,'reason':'FRESH_AUTHENTICATED_READ_REQUIRED'})
    positions=ObservationSource({'available':False,'reason':'POST_GENESIS_INVENTORY_READ_REQUIRED'})
    geo=ObservationSource({'available':False,'reason':'FRESH_GEOBLOCK_REQUIRED'})
    book=BookStateSource();reconciliation={'phase':'BLOCKED','reconciled':False,'reason':'MANUAL_TARGET_REQUIRED'}
    generation=None
    local={};inventory_meta={};storage_ok=False;stage='LOCAL_LEDGER_VALIDATION'
    try:
        if any(os.getenv(k,'false').strip().lower()!='false' for k in FLAGS):raise ValueError('FLAGS')
        prior=read_genesis(LEDGER);local=dict(prior)
        if target:
            stage='ARCHIVE_RPC_CONFIGURATION'
            endpoint=os.getenv('POLYGON_ARCHIVE_RPC_URL')
            validate_rpc_endpoint(endpoint)
            wallet=expected_wallet()
            if prior['snapshot']['wallet'].lower()!=wallet.lower() or prior['snapshot']['collateral']['contract']!=CONTRACT:raise ValueError('BASELINE_BINDING')
            if prior['phase']!='GENESIS_RECONCILED' or prior['event_count']!=0:raise ValueError('LEDGER_REQUIRES_EVENT_PROJECTION_OR_RECOVERY')
            stage='POST_GENESIS_CTF_DISCOVERY'
            rpc=PublicRPC(wallet,endpoint=endpoint);rpc.log_window=10
            inventory=await asyncio.to_thread(incremental_inventory,rpc,prior)
            inventory_meta=inventory_metadata(inventory)
            if inventory['events_count'] or any(int(x)>0 for x in inventory['balances'].values()):
                reconciliation={'phase':'RECOVERY_REQUIRED','reconciled':False,'reason':'POST_GENESIS_CONDITIONAL_ACTIVITY_UNEXPLAINED'}
            else:
                stage='EXISTING_L2_BINDING'
                creds,storage=load_existing(ROOT)
                if not creds or storage.get('storage_validated') is not True:raise ValueError('L2_STORAGE_BINDING_UNAVAILABLE')
                storage_ok=True
                from polymarket._internal.hmac import build_hmac_signature
                from polymarket._internal.environment import PRODUCTION_CONFIG as env
                if env.chain_id!=137 or env.collateral_token!=CONTRACT:raise ValueError('SDK_ENVIRONMENT_MISMATCH')
                stage='CLOB_TIME_PREFLIGHT'
                stamp=await GetOnlyTransport(CLOB,('/time',),audit=audit).get_json('/time')
                if type(stamp) is not int or abs(time.time()-stamp)>5:raise ValueError('CLOCK')
                async def headers(path):
                    if path not in ('/balance-allowance','/data/orders','/data/trades'):raise ValueError('GET_ROUTE')
                    stamp=int(time.time())
                    return {'POLY_ADDRESS':EXPECTED,'POLY_API_KEY':creds['apiKey'],'POLY_PASSPHRASE':creds['passphrase'],
                            'POLY_TIMESTAMP':str(stamp),'POLY_SIGNATURE':build_hmac_signature(secret=creds['secret'],timestamp=stamp,method='GET',path=path,body=None)}
                client=ReadOnlyClient(wallet=wallet,signature_type=3,
                    clob=GetOnlyTransport(CLOB,('/balance-allowance','/data/orders','/data/trades'),headers=headers,audit=audit),
                    data=GetOnlyTransport(DATA,('/v2/positions',),audit=audit))
                try:
                    book=await discover_book(audit);task=asyncio.create_task(book.run())
                    # A bounded warmup does not refresh any source timestamp.
                    deadline=time.monotonic()+8
                    while not task.done() and not book.read()['available'] and time.monotonic()<deadline:await asyncio.sleep(.05)
                except Exception:book=BookStateSource()
                geo_reader=GeoBlockSource(fetch=lambda:GetOnlyTransport('https://polymarket.com',('/api/geoblock',),audit=audit).get_json('/api/geoblock'))
                stage='PREPARE_CTF_THEN_PARALLEL_ACCOUNT_GENERATION'
                observed,geoval,inventory=await acquire_final_views(client,geo_reader,rpc,prior,inventory)
                inventory_meta=inventory_metadata(inventory)
                geo=ObservationSource(geoval)
                stage='REMOTE_LOCAL_RECONCILIATION'
                bal=plain(observed['balance'][0]);raw=str(bal['balance'])
                allowed=[v for k,v in bal['allowances'].items() if k.lower()==env.standard_exchange.lower()]
                if len(allowed)!=1:raise ValueError('ALLOWANCE_SPENDER')
                a_stamp=min(observed[n][1] for n in ('balance','orders','trades'))
                remote={'wallet':wallet,'balance_raw':raw,'orders':observed['orders'][0],'trades':observed['trades'][0],
                    'positions':observed['positions'][0],'balances':inventory['balances'],'events_count':inventory['events_count'],
                    'complete':True,'observed_ms':min(a_stamp,observed['positions'][1],inventory['observed_ms'])}
                current=read_genesis(LEDGER)
                if current['last_hash']!=prior['last_hash']:raise ValueError('LEDGER_CHANGED_DURING_READ')
                generation_id=inventory.get('generation_attempt',1)
                generation={'id':generation_id,'ledger_hash':current['last_hash'],
                    'watermark':{'block_number':inventory['to_block'],'block_hash':inventory['block_hash']},
                    'components':{n:{'generation':generation_id,'observed_ms':observed[n][1],'complete':True} for n in observed}}
                generation['components']['inventory']={'generation':generation_id,'observed_ms':inventory['observed_ms'],'complete':True}
                reconciliation=evaluate_baseline(current,remote,now=now_ms())
                gate=validate_generation(generation,now_ms())
                if not gate['complete'] and reconciliation['phase']!='RECOVERY_REQUIRED':
                    reconciliation={'phase':'BLOCKED','reconciled':False,'reason':gate['reason'],'generation':gate}
                complete=reconciliation['reconciled']
                account=ObservationSource({'available':True,'authenticated':True,'observed_ms':a_stamp,'balance_collateral':str(units(raw)),
                    'allowance_collateral':str(units(allowed[0])),'collateral_symbol':'pUSD','open_order_ids':[] if not remote['orders'] else ['REDACTED'],
                    'complete':complete,'pagination_complete':True,'provenance':'EXISTING_BOUND_L2_SIGNATURE_TYPE_3_PARALLEL_GETS',
                    'scope':'CREDENTIAL_VIEW_WITH_SCOPED_GENESIS','reason':reconciliation.get('reason')})
                positions=ObservationSource({'available':True,'observed_ms':remote['observed_ms'],'balances':inventory['balances'],
                    'complete':complete,'provenance':'GENESIS_PLUS_INCREMENTAL_CTF_AND_PAGINATED_INDEXER','reason':reconciliation.get('reason')})
                local={**current,'reconciled_now':complete}
            if reconciliation['phase']=='RECOVERY_REQUIRED':
                append_activity(LEDGER,'RECOVERY_REQUIRED',{'reason':reconciliation['reason']})
                local=read_genesis(LEDGER)
    except Exception:
        reconciliation={'phase':'BLOCKED','reconciled':False,'reason':'SOURCE_OR_LEDGER_UNAVAILABLE_NO_FALLBACK','failed_stage':stage}
    def final_local():
        current=read_genesis(LEDGER)
        if not prior or current['last_hash']!=local.get('last_hash'):
            return {'phase':'RECOVERY_REQUIRED','reconciled_now':False}
        return {**current,'reconciled_now':local.get('reconciled_now') is True}
    risk=ForwardSessionRiskSource(reconciliation,now_ms)
    try:
        readiness=await ProductionReadinessCheck(account=account,positions=positions,book=book,geo=geo,risk=risk,
            local_reader=final_local,collateral_unit='pUSD',generation=generation).run()
        report={'phase':'D6_POST_GENESIS_READ_ONLY','readiness':annotate(readiness),'reconciliation':reconciliation,
            'genesis_created':False,'genesis_snapshot_sha256':prior['snapshot_sha256'] if prior else None,
            'genesis_unchanged':bool(prior and read_genesis(LEDGER)['snapshot_sha256']==prior['snapshot_sha256']),
            'inventory_incremental':inventory_meta,'coverage_limitations':LIMITS,'rpc_calls':rpc.calls if rpc else [],'get_requests':audit,
            'storage_binding_verified':storage_ok,'private_key_loaded':False,'l1_signature_produced':False,
            'future_execution_binding_ready':False,'network_mode':'MANUAL_TARGET' if target else 'OFFLINE',
            'btc_v1_sha256':hashlib.sha256((ROOT/'analysis/d6/paper_live.py').read_bytes()).hexdigest()}
        if creds and any(v in json.dumps(report) for v in creds.values()):raise ValueError('REDACTION_FAILED')
        return report
    finally:
        if task:
            task.cancel();await asyncio.gather(task,return_exceptions=True)


def main():
    if sys.argv[1:] not in (['--offline'],['--target-machine']):return 2
    try:report=asyncio.run(run(sys.argv[1]=='--target-machine'))
    except BaseException:report={'phase':'D6_POST_GENESIS_READ_ONLY','status':'BLOCKED','ready_for_arm':False,'submit_allowed':False}
    path=ROOT/('D6_POST_GENESIS_READINESS_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    write_report(path,report);print(json.dumps(report,indent=2));print('REPORT_FILE='+path.name)

if __name__=='__main__':raise SystemExit(main())
