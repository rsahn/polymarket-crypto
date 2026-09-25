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
from app.live.freshness_policy import freshness_policy,freshness_limit_ms,stale_reason
from app.live.latency_trace import diagnose, measured_await
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


def load_inventory_cursor(root,prior):
    """Resume local evidence only. Missing/unusable cursor never triggers genesis scan.
    Legacy redacted reports can seed only a proven empty scoped inventory.
    """
    candidates=[]
    paths=list((root/'runtime/d6_inventory_cursors').glob('*.json'))+list(root.glob('D6_POST_GENESIS_READINESS_*.json'))
    for path in paths:
        try:
            r=json.loads(path.read_text(encoding='utf-8-sig'))
            if r.get('genesis_snapshot_sha256')!=prior['snapshot_sha256'] or r.get('genesis_unchanged') is not True:continue
            x=r['inventory_incremental']
            if r.get('cursor_schema')==1:
                from app.live.genesis_ledger import digest
                if digest(x)!=r['inventory_sha256']:raise ValueError('CURSOR_INTEGRITY')
            else:
                if r.get('network_mode')!='MANUAL_TARGET' or x['events_count']!=0 or x['assets_checked']!=0:continue
                x={**x,'balances':{},'status':'PASS_SCOPED_READS'}
            if x.get('status')!='PASS_SCOPED_READS':continue
            if type(x['from_block']) is not int or x['from_block']!=prior['snapshot']['block_number']+1:continue
            if type(x['to_block']) is not int or x['to_block']<x['from_block']:continue
            if type(x['observed_ms']) is not int or not isinstance(x['balances'],dict):continue
            if len(x['block_hash'])!=66 or not x['block_hash'].startswith('0x'):continue
            int(x['block_hash'][2:],16)
            candidates.append(x)
        except (KeyError,TypeError,ValueError):
            if path.parent.name=='d6_inventory_cursors':raise ValueError('CURSOR_INTEGRITY') from None
            continue
    if not candidates:raise ValueError('INVENTORY_CURSOR_REQUIRED')
    highest=max(x['to_block'] for x in candidates)
    top=[x for x in candidates if x['to_block']==highest]
    if len({x['block_hash'] for x in top})!=1:raise ValueError('CURSOR_CONFLICT')
    return max(top,key=lambda x:x['observed_ms'])


def save_inventory_cursor(root,prior,inventory):
    import tempfile
    import uuid
    from app.live.genesis_ledger import digest
    folder=root/'runtime/d6_inventory_cursors';folder.mkdir(parents=True,exist_ok=True)
    value={'cursor_schema':1,'genesis_snapshot_sha256':prior['snapshot_sha256'],'genesis_unchanged':True,
           'inventory_incremental':inventory,'inventory_sha256':digest(inventory)}
    target=folder/(str(inventory['to_block'])+'_'+uuid.uuid4().hex+'.json')
    fd,tmp=tempfile.mkstemp(dir=folder,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(value,f);f.flush();os.fsync(f.fileno())
        os.link(tmp,target)  # atomic publication, no overwrite
    finally:os.unlink(tmp)


def advance_inventory(rpc,prior,previous):
    """Fix the final block ONCE; scan only cursor+1..that block."""
    anchor=rpc.call('eth_getBlockByNumber',[hex(previous['to_block']),False])
    if anchor['hash']!=previous['block_hash']:raise ValueError('CURSOR_REORG')
    current=rpc.call('eth_getBlockByNumber',['latest',False]);end=int(current['number'],16)
    if end<previous['to_block']:raise ValueError('HEAD_REGRESSION')
    if end==previous['to_block']:
        if current['hash']!=previous['block_hash']:raise ValueError('CURSOR_REORG')
        return previous
    captured={};started=now_ms()
    result=scan_ctf(rpc,previous['to_block']+1,end,set(previous['balances']),capture=captured)
    if result['status']!='PASS_SCOPED_READS' or result['block_hash']!=current['hash']:raise ValueError('INCREMENTAL_SCAN_FAILED')
    return {**result,'from_block':previous['from_block'],'balances':captured['balances'],
            'events_count':previous['events_count']+result['events_count'],
            'observed_ms':min(started,int(current['timestamp'],16)*1000),
            'provenance':'POST_GENESIS_CTF_INCOMING_EVENTS_AND_ANCHORED_BALANCES'}


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


async def fresh_views(client,*,drain_errors=False):
    async def observed(label,coro):
        started=now_ms();value=await measured_await('account.'+label,coro)
        return value,started
    values=await asyncio.gather(
        observed('balance',client.get_balance_allowance(asset_type='COLLATERAL')),
        observed('orders',drain(client.list_open_orders())),observed('trades',drain(client.list_account_trades())),
        observed('positions',drain(client.list_positions(user=client.wallet,full_history=True,include_archived=True,filter_type='TOKENS',filter_amount=0))),
        return_exceptions=drain_errors)
    for value in values:
        if isinstance(value,BaseException):raise value
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


async def acquire_final_views(client,geo_reader,rpc,prior,inventory,*,checkpoint=None,attempts=None):
    # Catch-up is preparation. The final remote head witness runs alongside GETs.
    geoval=await geo_reader.read()
    for attempt in range(1,4):
        inventory=await asyncio.to_thread(advance_inventory,rpc,prior,inventory)
        if checkpoint:checkpoint(inventory)
        results=await asyncio.gather(fresh_views(client),asyncio.to_thread(witness_inventory,rpc,inventory),return_exceptions=True)
        observed,witness=results
        known={'HEAD_ADVANCED','HEAD_REGRESSION','CURSOR_REORG','FUTURE_BLOCK'}
        reason=witness.args[0] if isinstance(witness,ValueError) and witness.args and witness.args[0] in known else 'INVENTORY_WITNESS_FAILED' if isinstance(witness,BaseException) else 'WITNESS_MATCHED'
        if attempts is not None:attempts.append({'attempt':attempt,'watermark_block':inventory['to_block'],
            'watermark_hash':inventory['block_hash'],'scan_observed_ms':inventory['observed_ms'],'reason':reason,
            'account_complete':not isinstance(observed,BaseException)})
        if isinstance(observed,BaseException):raise ValueError('ACCOUNT_GENERATION_FAILED') from None
        if isinstance(witness,ValueError) and witness.args==('HEAD_ADVANCED',):continue
        if isinstance(witness,BaseException):raise ValueError('INVENTORY_WITNESS_FAILED') from None
        return observed,geoval,{**witness,'generation_attempt':attempt}
    raise ValueError('HEAD_ADVANCED_GENERATION_RETRY_LIMIT')


def inventory_metadata(inventory):
    return {k:inventory[k] for k in ('from_block','to_block','block_hash','events_count','assets_checked','observed_ms','provenance',
        'scan_observed_ms','head_witness_started_ms','head_witness_finished_ms','head_block_timestamp_ms',
        'head_unchanged_verified','generation_attempt','post_b_proof','finalized_block','finalized_hash','critical_path','boundary_evidence','cursor_previous','anchor_catchup_ranges') if k in inventory}


def inventory_completeness(inventory):
    """Report the missing scope proof independently of the latency verdict."""
    proof=(inventory or {}).get('post_b_proof',{})
    return dict(evidence_available=bool(proof),
        inventory_through_C_proven=proof.get('inventory_through_C_proven') is True,
        current_inventory_proven=proof.get('current_inventory_proven') is True,
        post_C_completeness='UNPROVEN_NO_COMMON_WATERMARK' if proof else 'NO_BOUNDARY_EVIDENCE',
        generation_stale=proof.get('reason')==stale_reason('GENERATION'),
        boundary_verdict=proof.get('reason'),latency_fix_sufficient=False)


def annotate(readiness):
    source_for={'wallet_auth':'account','balance_pusd':'account','allowance_pusd':'account','open_orders':'account',
        'inventory':'positions','account_reconciliation':'positions','session_risk':'risk','book_freshness':'book','geoblock':'geo'}
    at=readiness['evaluated_ms'];details={}
    for name,passed in readiness['checks'].items():
        source=source_for.get(name,'local');o=readiness['observations'].get(source,{})
        details[name]={'status':'PASS' if passed else 'BLOCKED','source':o.get('provenance',o.get('source',source)),
            'observed_ms':o.get('observed_ms'),'evaluated_ms':at,
            'reason':'INVARIANT_SATISFIED' if passed else o.get('reason') or 'MISSING_STALE_OR_UNRECONCILED',
            'freshness_limit_ms':60000 if name=='geoblock' else freshness_limit_ms() if source!='local' else None}
    readiness['check_details']=details
    for obs in readiness['observations'].values():
        for key in ('wallet','open_order_ids','balances','books'):obs.pop(key,None)
    return readiness


async def run(target=False,*,health_contract=False):
    audit=[];rpc=None;creds=None;task=None;prior=None;pooled_transports=[];worker_timing={}
    account=ObservationSource({'available':False,'reason':'FRESH_AUTHENTICATED_READ_REQUIRED'})
    positions=ObservationSource({'available':False,'reason':'POST_GENESIS_INVENTORY_READ_REQUIRED'})
    geo=ObservationSource({'available':False,'reason':'FRESH_GEOBLOCK_REQUIRED'})
    book=BookStateSource();reconciliation={'phase':'BLOCKED','reconciled':False,'reason':'MANUAL_TARGET_REQUIRED'}
    generation=None
    pending_inventory_checkpoint=None;inventory=None
    preparation_rpc=None;current_generation_inventory=None
    connection_warmup={'status':'NOT_RUN'}
    attempts=[];qualified=None;clock_diagnostic={};reconciliation_timing={}
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
            if health_contract:
                clock_start=now_ms()
                server=await GetOnlyTransport(CLOB,('/time',),audit=audit).get_json('/time')
                clock_end=now_ms()
                if type(server) is not int:raise ValueError('CLOCK')
                clock_diagnostic={'source':'LOCAL_TIME_TIME_NS_UTC','clob_server_seconds':server,
                    'request_started_ms':clock_start,'response_received_ms':clock_end,
                    'server_second_minus_local_receive_ms':server*1000-clock_end,
                    'offset_interval_ms':[server*1000-clock_end,(server+1)*1000-clock_start],
                    'accuracy_500ms_proven':False,'timestamps_adjusted':False}
            stage='POST_GENESIS_CTF_DISCOVERY'
            rpc=PublicRPC(wallet,endpoint=endpoint,allow_finalized=health_contract,pooled=health_contract);rpc.log_window=10
            rpc.parallel_inventory_reads=health_contract
            inventory=load_inventory_cursor(ROOT,prior)
            if health_contract:
                from analysis.qualify_post_b_proofs import prepare_finalized_inventory,acquire_post_b
                from app.live.preparation_rpc import PreparationRPC
                preparation_rpc=PreparationRPC(rpc)
                inventory,qualified=await asyncio.to_thread(prepare_finalized_inventory,preparation_rpc,prior,inventory)
            else:
                anchor=await asyncio.to_thread(rpc.call,'eth_getBlockByNumber',[hex(prior['snapshot']['block_number']),False])
                if anchor['hash']!=prior['snapshot']['block_hash']:raise ValueError('GENESIS_ANCHOR_CHANGED')
                inventory=await asyncio.to_thread(advance_inventory,rpc,prior,inventory)
            save_inventory_cursor(ROOT,prior,inventory)
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
                clock_start=now_ms()
                stamp=await GetOnlyTransport(CLOB,('/time',),audit=audit).get_json('/time')
                clock_end=now_ms()
                clock_diagnostic={'source':'LOCAL_TIME_TIME_NS_UTC','clob_server_seconds':stamp if type(stamp) is int else None,
                    'request_started_ms':clock_start,'response_received_ms':clock_end,'accuracy_500ms_proven':False,
                    'server_second_minus_local_receive_ms':stamp*1000-clock_end if type(stamp) is int else None,
                    'offset_interval_ms':[stamp*1000-clock_end,(stamp+1)*1000-clock_start] if type(stamp) is int else None,
                    'note':'CLOB integer-second reading is diagnostic, not a subsecond clock calibration; no timestamps adjusted'}
                if type(stamp) is not int or abs(time.time()-stamp)>5:raise ValueError('CLOCK')
                async def headers(path):
                    if path not in ('/balance-allowance','/data/orders','/data/trades'):raise ValueError('GET_ROUTE')
                    stamp=int(time.time())
                    return {'POLY_ADDRESS':EXPECTED,'POLY_API_KEY':creds['apiKey'],'POLY_PASSPHRASE':creds['passphrase'],
                            'POLY_TIMESTAMP':str(stamp),'POLY_SIGNATURE':build_hmac_signature(secret=creds['secret'],timestamp=stamp,method='GET',path=path,body=None)}
                def transport(base,routes,**kw):
                    t=GetOnlyTransport(base,routes,pooled=health_contract,**kw)
                    pooled_transports.append(t);return t
                client=ReadOnlyClient(wallet=wallet,signature_type=3,
                    clob=transport(CLOB,('/balance-allowance','/data/orders','/data/trades'),headers=headers,audit=audit),
                    data=transport(DATA,('/v2/positions',),audit=audit))
                if health_contract:
                    stage='READ_ONLY_CONNECTION_WARMUP'
                    if (getattr(rpc,'pool',None) is not None and
                            getattr(getattr(client,'clob',None),'pool',None) is not None and
                            getattr(getattr(client,'data',None),'pool',None) is not None):
                        from app.live.readonly_warmup import warm_readonly
                        connection_warmup=await warm_readonly(rpc,lambda:fresh_views(client,drain_errors=True))
                    else:
                        connection_warmup={'status':'SKIPPED_NO_PERSISTENT_POOLS'}
                try:
                    book=await discover_book(audit)
                    from app.live.ws_recovery import run_with_recovery
                    task=asyncio.create_task(run_with_recovery(book) if health_contract else book.run())
                    # A bounded warmup does not refresh any source timestamp.
                    deadline=time.monotonic()+8
                    while not task.done() and not book.read()['synchronized'] and time.monotonic()<deadline:await asyncio.sleep(.05)
                except Exception:book=BookStateSource()
                geo_reader=GeoBlockSource(fetch=lambda:GetOnlyTransport('https://polymarket.com',('/api/geoblock',),audit=audit).get_json('/api/geoblock'))
                stage='PREPARE_CTF_THEN_PARALLEL_ACCOUNT_GENERATION'
                if health_contract:
                    from app.live.generation_worker import run_generation_worker
                    anchored_inventory=inventory
                    values,worker_timing=await run_generation_worker(
                        lambda:acquire_post_b(client,geo_reader,rpc,anchored_inventory,qualified,attempts=attempts))
                    observed,geoval,inventory=values
                    pending_inventory_checkpoint=inventory
                else:
                    observed,geoval,inventory=await acquire_final_views(client,geo_reader,rpc,prior,inventory,checkpoint=lambda x:save_inventory_cursor(ROOT,prior,x),attempts=attempts)
                current_generation_inventory=inventory
                # Metadata formatting is deferred until after evaluation.
                geo=ObservationSource(geoval)
                stage='REMOTE_LOCAL_RECONCILIATION'
                reconciliation_started=now_ms();reconciliation_cpu=time.thread_time_ns()
                bal=plain(observed['balance'][0]);raw=str(bal['balance'])
                allowed=[v for k,v in bal['allowances'].items() if k.lower()==env.standard_exchange.lower()]
                if len(allowed)!=1:raise ValueError('ALLOWANCE_SPENDER')
                a_stamp=min(observed[n][1] for n in ('balance','orders','trades'))
                remote={'wallet':wallet,'balance_raw':raw,'orders':observed['orders'][0],'trades':observed['trades'][0],
                    'positions':observed['positions'][0],'balances':inventory['balances'],'events_count':inventory['events_count'],
                    'complete':(not health_contract or inventory.get('post_b_proof',{}).get('current_inventory_proven') is True),'observed_ms':min(a_stamp,observed['positions'][1],inventory['observed_ms'])}
                current=read_genesis(LEDGER)
                if current['last_hash']!=prior['last_hash']:raise ValueError('LEDGER_CHANGED_DURING_READ')
                generation_id=inventory.get('generation_attempt',1)
                generation={'id':generation_id,'ledger_hash':current['last_hash'],
                    'watermark':{'block_number':inventory['to_block'],'block_hash':inventory['block_hash']},
                    'components':{n:{'generation':generation_id,'observed_ms':observed[n][1],'complete':True} for n in observed}}
                generation['components']['inventory']={'generation':generation_id,'observed_ms':inventory['observed_ms'],'complete':remote['complete']}
                reconciliation=evaluate_baseline(current,remote,now=now_ms())
                if health_contract and (any(remote[n] for n in ('orders','trades','positions'))
                        or remote['balance_raw']!=current['snapshot']['collateral']['balance_raw']
                        or remote['events_count'] or any(int(v) for v in remote['balances'].values())):
                    reconciliation={'phase':'RECOVERY_REQUIRED','reconciled':False,'reason':'REMOTE_ACTIVITY_UNEXPLAINED'}
                gate=validate_generation(generation,now_ms())
                if not gate['complete'] and reconciliation['phase']!='RECOVERY_REQUIRED':
                    reconciliation={'phase':'BLOCKED','reconciled':False,'reason':gate['reason'],'generation':gate}
                if health_contract and not remote['complete'] and reconciliation['phase']!='RECOVERY_REQUIRED':
                    reconciliation={'phase':'BLOCKED','reconciled':False,
                        'reason':inventory.get('post_b_proof',{}).get('reason','POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN'),
                        'boundary_proof':inventory.get('post_b_proof',{})}
                complete=reconciliation['reconciled']
                account=ObservationSource({'available':True,'authenticated':True,'observed_ms':a_stamp,'balance_collateral':str(units(raw)),
                    'allowance_collateral':str(units(allowed[0])),'collateral_symbol':'pUSD','open_order_ids':[] if not remote['orders'] else ['REDACTED'],
                    'complete':complete,'pagination_complete':True,'provenance':'EXISTING_BOUND_L2_SIGNATURE_TYPE_3_PARALLEL_GETS',
                    'scope':'CREDENTIAL_VIEW_WITH_SCOPED_GENESIS','reason':reconciliation.get('reason')})
                positions=ObservationSource({'available':True,'observed_ms':remote['observed_ms'],'balances':inventory['balances'],
                    'complete':complete,'provenance':'GENESIS_PLUS_INCREMENTAL_CTF_AND_PAGINATED_INDEXER','reason':reconciliation.get('reason')})
                local={**current,'reconciled_now':complete}
                reconciliation_timing={'started_ms':reconciliation_started,'finished_ms':now_ms(),
                    'thread_cpu_ms':(time.thread_time_ns()-reconciliation_cpu)/1000000}
            if reconciliation['phase']=='RECOVERY_REQUIRED' and not health_contract:
                append_activity(LEDGER,'RECOVERY_REQUIRED',{'reason':reconciliation['reason']})
                local=read_genesis(LEDGER)
    except Exception as exc:
        allowed={'READ_ONLY_WARMUP_FAILED','BOUNDARY_SCHEMA_INVALID','COVERAGE_GAP_OR_OVERLAP','RPC_PARTIAL','BOUNDARY_REORG','CURSOR_BOUNDARY_INCOHERENT','FINALIZED_UNPROVEN','CURSOR_AHEAD_OF_FINALIZED','RECOVERY_REQUIRED','TAIL_SCAN_FAILED','POST_B_TAIL_ADVANCED','TAIL_REORG','ANCHOR_REORG','GENERATION_STALE_500MS','GENERATION_STALE_1300MS','ACCOUNT_GENERATION_PARTIAL','HEAD_ADVANCED_GENERATION_RETRY_LIMIT','INVENTORY_CURSOR_REQUIRED','CURSOR_CONFLICT','CURSOR_INTEGRITY','CURSOR_REORG','GENESIS_ANCHOR_CHANGED','ACCOUNT_GENERATION_FAILED','INVENTORY_WITNESS_FAILED','INCREMENTAL_SCAN_FAILED','HEAD_REGRESSION'}
        reason=exc.args[0] if exc.args and isinstance(exc.args[0],str) and exc.args[0] in allowed else 'SOURCE_OR_LEDGER_UNAVAILABLE_NO_FALLBACK'
        if stage=='POST_GENESIS_CTF_DISCOVERY' and preparation_rpc is not None and preparation_rpc.failure:
            reason=preparation_rpc.failure
        reconciliation={'phase':'RECOVERY_REQUIRED' if reason=='RECOVERY_REQUIRED' else 'BLOCKED','reconciled':False,'reason':reason,'failed_stage':stage}
    def final_local():
        current=read_genesis(LEDGER)
        if not prior or current['last_hash']!=local.get('last_hash'):
            return {'phase':'RECOVERY_REQUIRED','reconciled_now':False}
        return {**current,'reconciled_now':local.get('reconciled_now') is True}
    risk=ForwardSessionRiskSource(reconciliation,now_ms)
    try:
        readiness=await ProductionReadinessCheck(account=account,positions=positions,book=book,geo=geo,risk=risk,
            local_reader=final_local,collateral_unit='pUSD',generation=generation).run()
        if inventory is not None:inventory_meta=inventory_metadata(inventory)
        if current_generation_inventory is None:
            # Retain cursor facts, but never label a previous run's proof/timings as current.
            inventory_meta={k:v for k,v in inventory_meta.items() if k in (
                'from_block','to_block','block_hash','events_count','assets_checked','observed_ms','provenance')}
        path=(current_generation_inventory or {}).get('critical_path',{})
        evaluated=readiness['evaluated_ms']
        account_obs=readiness.get('observations',{}).get('account',{}).get('observed_ms')
        book_obs=readiness.get('observations',{}).get('book',{}).get('observed_ms')
        final_budget={'inventory_age_at_evaluation_ms':evaluated-path['scan_observed_ms'] if 'scan_observed_ms' in path else None,
            'account_age_at_evaluation_ms':evaluated-account_obs if account_obs is not None else None,
            'book_age_at_evaluation_ms':evaluated-book_obs if book_obs is not None else None,
            'critical_path_wall_ms':evaluated-path['scan_dispatch_ms'] if 'scan_dispatch_ms' in path else None}
        # Persist only after the decision snapshot; disk I/O cannot age its sources.
        persistence_started_ms=now_ms()
        checkpoint_status='NOT_PENDING'
        if pending_inventory_checkpoint is not None:
            try:
                save_inventory_cursor(ROOT,prior,pending_inventory_checkpoint)
                checkpoint_status='SAVED_AFTER_EVALUATION'
            except Exception:checkpoint_status='SAVE_FAILED_NO_GENESIS_CHANGE'
        persistence_finished_ms=now_ms()
        scheduler_timing={
            'generation_started_ms':worker_timing.get('generation_started_ms'),
            'inventory_final_proof_ms':path.get('scan_worker_finished_ms'),
            'account_started_ms':path.get('account_started_ms'),'account_finished_ms':path.get('account_finished_ms'),
            'recheck_started_ms':path.get('recheck_started_ms'),'recheck_finished_ms':path.get('recheck_finished_ms'),
            'join_finished_ms':worker_timing.get('generation_result_ready_ms'),
            'reconciliation_started_ms':reconciliation_timing.get('started_ms'),
            'reconciliation_finished_ms':reconciliation_timing.get('finished_ms'),
            'book_sample_started_ms':readiness.get('book_sample_started_ms'),
            'book_sample_finished_ms':readiness.get('book_sample_finished_ms'),
            'evaluation_started_ms':readiness.get('evaluation_started_ms'),
            'evaluation_finished_ms':readiness.get('evaluation_complete_ms'),
            'post_evaluation_persistence_started_ms':persistence_started_ms,
            'post_evaluation_persistence_finished_ms':persistence_finished_ms,
            'account_recheck_execution':'SEQUENTIAL_POST_ACCOUNT_CANONICAL_WITNESS',
            'scheduler_overhead_before_evaluation_ms':None,
            'scheduler_overhead_scope':'TOTAL_NOT_ISOLATED_FROM_BUSINESS_CPU; SEE_MEASURED_RESUME_DELAYS',
            'measured_scan_resume_delay_ms':path.get('scan_resume_delay_ms'),
            'measured_generation_continuation_delay_ms':worker_timing.get('continuation_delay_ms')}
        report={'phase':'D6_POST_GENESIS_READ_ONLY','readiness':annotate(readiness),'reconciliation':reconciliation,
            'genesis_created':False,'genesis_snapshot_sha256':prior['snapshot_sha256'] if prior else None,
            'genesis_unchanged':bool(prior and read_genesis(LEDGER)['snapshot_sha256']==prior['snapshot_sha256']),
            'inventory_completeness':inventory_completeness(current_generation_inventory) if health_contract else None,
            'inventory_evidence_origin':'CURRENT_GENERATION' if current_generation_inventory is not None else 'PREPARATION_OR_PRIOR_CURSOR',
            'preparation_rpc_policy':preparation_rpc.report() if preparation_rpc is not None else None,
            'connection_warmup':connection_warmup,
            'inventory_incremental':inventory_meta,'generation_attempts':attempts,'coverage_limitations':LIMITS,'rpc_calls':rpc.calls if rpc else [],'get_requests':audit,
            'storage_binding_verified':storage_ok,'private_key_loaded':False,'l1_signature_produced':False,
            'finalized_qualification':qualified,'clock_diagnostic':clock_diagnostic,'health_contract':health_contract,
            'scheduler_timing':scheduler_timing,'generation_worker_timing':worker_timing,'final_timing_budget':final_budget,'reconciliation_timing':reconciliation_timing,'inventory_checkpoint_status':checkpoint_status,'future_execution_binding_ready':False,'network_mode':'MANUAL_TARGET' if target else 'OFFLINE',
            'btc_v1_sha256':hashlib.sha256((ROOT/'analysis/d6/paper_live.py').read_bytes()).hexdigest()}
        if creds and any(v in json.dumps(report) for v in creds.values()):raise ValueError('REDACTION_FAILED')
        return report
    finally:
        for transport in pooled_transports:
            if hasattr(transport,'close'):transport.close()
        if rpc and hasattr(rpc,'close'):rpc.close()
        if task:
            task.cancel();await asyncio.gather(task,return_exceptions=True)


def main():
    args=sys.argv[1:]
    limit=500
    if '--freshness-ms' in args:
        i=args.index('--freshness-ms')
        if i+1>=len(args) or args[i+1] not in ('500','1300'):return 2
        limit=int(args[i+1]);args=args[:i]+args[i+2:]
    diagnostic='--diagnostics' in args
    if diagnostic:args=[a for a in args if a!='--diagnostics']
    if args not in (['--offline'],['--target-machine'],['--target-machine','--health-contract']):return 2
    if diagnostic and args!=['--target-machine','--health-contract']:return 2
    runner=diagnose(run) if diagnostic else run
    try:
        with freshness_policy(limit):
            report=asyncio.run(runner(args[0]=='--target-machine',health_contract='--health-contract' in args))
        report['freshness_limit_ms']=limit
    except BaseException:report={'phase':'D6_POST_GENESIS_READ_ONLY','status':'BLOCKED','ready_for_arm':False,'submit_allowed':False}
    path=ROOT/('D6_POST_GENESIS_READINESS_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    write_report(path,report);print(json.dumps(report,indent=2));print('REPORT_FILE='+path.name)

if __name__=='__main__':raise SystemExit(main())
