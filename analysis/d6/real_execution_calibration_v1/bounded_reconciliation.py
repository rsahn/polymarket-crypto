"""Read-only bounded experiment verifier. Never calls Ledger.reconcile or arms.
A verified bounded window is not a full-wallet atomic snapshot. No default authority.
"""
import re,copy
from fractions import Fraction
from decimal import Decimal,localcontext
from .core import CalibrationLedger,digest,dec,VERSION
from .schemas import authenticate,integer
from .binding_consumer import require
from .compare_accounts import D6
from .identify_account import CONTRACT
from .log_schema import public_asset
from app.live.cash_evidence import reconcile_cash_delta

SCHEMA='BOUNDED_EXPERIMENT_RECONCILIATION/1'
SCOPE='EXPLICIT_EXPERIMENT_ASSETS_AND_INTENTS_NOT_FULL_WALLET'
REQUIRED=('baseline','closing','asset_mapping','coverage','finality','executions','terminal_orders','receipts','operator_declaration')

def raw(v):
    require(type(v) is str and re.fullmatch('0|[1-9][0-9]*',v) is not None and len(v)<=78,'RAW_UNIT_SCHEMA')
    n=int(v);require(n<2**256,'RAW_UNIT_RANGE');return n

def hashhex(v):require(type(v) is str and re.fullmatch('0x[0-9a-fA-F]{64}',v) is not None,'BLOCK_OR_TX_HASH');return v.lower()
def unique(v):require(type(v) is list and all(type(x) is str and x for x in v) and len(set(v))==len(v),'UNIQUE_IDS');return set(v)

def local_journal(path):
    recovery=CalibrationLedger.recover(path);rows=recovery['verified_rows'];require(bool(rows) and rows[0]['kind']=='INIT','JOURNAL_INIT')
    init=rows[0]['payload'];require(init['version']==VERSION and init['account']==D6,'JOURNAL_VERSION_ACCOUNT')
    orders={};fills={};reservations={};shadows={};stops=[];reserved=Decimal(0);reserves=0
    for row in rows:
        kind,p=row['kind'],row['payload']
        if kind=='SHADOW_SEALED':shadows[p['opportunity_id']]=p['shadow']
        if kind=='STOP':stops.append(p['reason'])
        if kind=='RESERVE':
            require(p['opportunity_id'] not in reservations,'DUPLICATE_RESERVATION');reservations[p['opportunity_id']]=copy.deepcopy(p)
            n,f=dec(p['notional']),dec(p['fee_ceiling']);require(0<n<=CalibrationLedger.MAX_ENTRY,'LOCAL_ENTRY_CAP')
            reserved+=n+f;reserves+=1
        if kind=='DURABLE_INTENT':
            cid=p['client_id'];require(type(cid) is str and cid and cid not in orders,'DUPLICATE_LOCAL_INTENT')
            op=p['opportunity_id'];require(op in reservations and op in shadows,'INTENT_WITHOUT_RESERVATION_OR_SHADOW')
            require(p['token']==shadows[op]['token'] and p['market']==shadows[op]['market'],'SEALED_INTENT_IDENTITY')
            require(p['order_type']=='FAK' and p['side'] in ('BUY','SELL') and 0<dec(p['price'])<1 and dec(p['shares'])>0,'LOCAL_INTENT_POLICY')
            if p['side']=='BUY':require(dec(p['notional'])<=CalibrationLedger.MAX_ENTRY and dec(p['price'])*dec(p['shares'])<=CalibrationLedger.MAX_ENTRY,'LOCAL_FORMATTED_ENTRY_CAP')
            orders[cid]={**copy.deepcopy(p),'order_id':None}
        if kind=='ACK_RESPONSE':
            cid=p['client_id'];require(cid in orders,'ACK_WITHOUT_INTENT');response=p['response']
            if type(response) is dict and response.get('ok') is True and type(response.get('order_id')) is str and response['order_id']:
                require(orders[cid]['order_id'] is None,'DUPLICATE_ACK');orders[cid]['order_id']=response['order_id']
        if kind=='FILL_OBSERVATION':
            f=p['fill'];tid=f['trade_id'];require(p['client_id'] in orders,'FILL_WITHOUT_INTENT')
            item={'client_id':p['client_id'],'fill':f}
            require(tid not in fills or fills[tid]==item,'LOCAL_FILL_CONFLICT');fills[tid]=item
    require(reserves<=CalibrationLedger.MAX_ENTRIES and reserved<=CalibrationLedger.MAX_TOTAL and len(orders)<=2*CalibrationLedger.MAX_ENTRIES,'LOCAL_EXPERIMENT_CAP')
    remote=[o['order_id'] for o in orders.values() if o['order_id']];require(len(remote)==len(set(remote)),'REMOTE_ORDER_ALIAS')
    return dict(experiment=rows[0]['experiment_id'],init=init,reservations=reservations,stops=stops,orders=orders,fills=fills,journal_digest=rows[-1]['hash'],unknown_intents=[k for k,o in orders.items() if o['order_id'] is None])

def asset_receipt_deltas(receipts,contract,tokens):
    from eth_utils import keccak
    single='0x'+keccak(text='TransferSingle(address,address,address,uint256,uint256)').hex()
    batch='0x'+keccak(text='TransferBatch(address,address,address,uint256[],uint256[])').hex()
    deltas={t:0 for t in tokens}
    for wrapper in receipts:
        for event in wrapper['receipt']['logs']:
            if event['address'].lower()!=contract.lower():continue
            topics=event['topics']
            if not topics or topics[0].lower() not in (single,batch):continue
            require(len(topics)==4 and all(type(t) is str and re.fullmatch('0x[0-9a-fA-F]{64}',t) for t in topics),'ASSET_TRANSFER_TOPICS')
            require(topics[2][2:26]==topics[3][2:26]=='0'*24,'ASSET_TRANSFER_ADDRESS')
            incoming=topics[3][-40:].lower()==D6[2:];outgoing=topics[2][-40:].lower()==D6[2:];sign=int(incoming)-int(outgoing)
            data=event['data'];require(type(data) is str and re.fullmatch('0x(?:[0-9a-fA-F]{64}){2,405}',data) is not None,'ASSET_TRANSFER_ABI')
            words=[int(data[i:i+64],16) for i in range(2,len(data),64)]
            if topics[0].lower()==single:
                require(len(words)==2,'TRANSFER_SINGLE_LENGTH');pairs=[(words[0],words[1])]
            else:
                require(len(words)>=4 and words[0]==64,'TRANSFER_BATCH_OFFSET')
                n=words[2];require(1<=n<=200 and words[1]==(3+n)*32 and len(words)==4+2*n and words[3+n]==n,'TRANSFER_BATCH_LENGTH')
                pairs=list(zip(words[3:3+n],words[4+n:]))
            for token_id,amount in pairs:
                if incoming or outgoing:
                    require(str(token_id) in deltas,'FOREIGN_ASSET_IN_RECEIPT');deltas[str(token_id)]+=sign*amount
    return deltas

def evaluate(path,bundle=None,*,authority=None,now_ms,expected_operator=None):
    out=dict(schema=SCHEMA,scope=SCOPE,status='UNKNOWN_CUSTODY_REQUIRED',account=D6,collateral=CONTRACT,submit_allowed=False,calibration_ready=False,full_wallet_atomicity_proven=False,other_producers_excluded=False,ledger_reconciled_flag_changed=False,STOP_NEW_ENTRIES=True,custody_review_required=True,required_records=list(REQUIRED),blockers=[])
    try:
        integer(now_ms);local=local_journal(path);out.update(experiment=local['experiment'],session=local['experiment'],journal_digest=local['journal_digest'],local_intent_count=len(local['orders']),unknown_local_intents=local['unknown_intents'])
        out['blockers'].extend('LOCAL_STOP:'+s for s in local['stops'])
        if local['unknown_intents']:out['blockers'].append('UNKNOWN_ORDER_OUTCOME_INCLUDING_UNACKNOWLEDGED_INTENT')
        if bundle is None or authority is None:
            out['blockers'].append('VERIFIED_BOUNDED_RECORDS_UNAVAILABLE');return out
        require(bundle.get('schema')==SCHEMA and bundle.get('scope')==SCOPE,'BOUNDED_SCHEMA_SCOPE')
        tokens=bundle['tokens'];require(type(tokens) is list and 1<=len(tokens)<=2 and len(set(tokens))==len(tokens) and all(public_asset(t) for t in tokens),'BOUNDED_ASSET_UNIVERSE')
        market=bundle['market'];hashhex(market)
        records={}
        for kind in REQUIRED:
            record=bundle.get(kind);require(type(record) is dict,'UNKNOWN_'+kind.upper())
            require(type(record.get('chain_id')) is int and record['chain_id']==137,'RECORD_CHAIN')
            require(record.get('kind')==kind and record.get('scope')==SCOPE and record.get('account')==D6 and record.get('experiment')==local['experiment'],'RECORD_CONTEXT')
            require(record.get('source_digest')==digest(record.get('payload')),'RECORD_DIGEST')
            authenticate(authority,record)  # provenance callback, not a self-issued pass bit
            records[kind]=record['payload']
        baseline,closing,coverage,finality=(records[k] for k in ('baseline','closing','coverage','finality'))
        asset=records['asset_mapping'];require(asset['market']==market and set(asset['tokens'])==set(tokens) and type(asset['share_decimals']) is int and asset['share_decimals']==6,'ASSET_MAPPING')
        require(type(asset['asset_contract']) is str and re.fullmatch('0x[0-9a-fA-F]{40}',asset['asset_contract']) is not None,'ASSET_CONTRACT')
        for snap in (baseline,closing):
            require(type(snap['chain_id']) is int and snap['chain_id']==137 and snap['collateral_contract']==CONTRACT and snap['asset_contract']==asset['asset_contract'],'SNAPSHOT_CONTRACT')
            require(snap.get('collateral_symbol')=='pUSD' and type(snap.get('collateral_decimals')) is int and snap['collateral_decimals']==6,'COLLATERAL_NATIVE_UNITS_UNKNOWN')
            require(set(snap['assets_raw'])==set(tokens),'SNAPSHOT_ASSET_SCOPE')
            for amount in [snap['cash_raw'],*snap['assets_raw'].values()]:raw(amount)
            integer(snap['block_number']);hashhex(snap['block_hash']);integer(snap['read_start_ms']);integer(snap['observed_ms'])
            require(snap['read_start_ms']<=snap['observed_ms']<=now_ms,'SNAPSHOT_TIME')
        lo,hi=baseline['block_number'],closing['block_number'];require(lo<=hi,'BLOCK_REGRESSION')
        require(now_ms-closing['read_start_ms']<=5000,'CLOSING_OLDEST_READ_STALE')
        require(dec(local['init']['starting_cash'])==Decimal(raw(baseline['cash_raw']))/1000000,'LEDGER_BASELINE_CASH')
        require(finality.get('policy')=='PROVIDER_FINALIZED_PLUS_HASH_RECHECK','FINALITY_POLICY_UNKNOWN')
        integer(finality['finalized_number']);integer(finality['read_start_ms']);integer(finality['observed_ms'])
        require(hi<=finality['finalized_number'] and finality['read_start_ms']<=finality['observed_ms']<=now_ms and now_ms-finality['read_start_ms']<=5000,'FINALITY_UNPROVEN_OR_STALE')
        integer(finality['recheck_read_start_ms'])
        require(closing['observed_ms']<=finality['recheck_read_start_ms']<=finality['observed_ms'],'CANONICAL_RECHECK_BEFORE_CLOSING')
        canonical=finality['canonical_hashes'];recheck=finality['rechecked_hashes']
        for n,h in canonical.items():require(recheck.get(n)==h,'REORG_OR_UNRECHECKED_BLOCK')
        for snap in (baseline,closing):require(canonical.get(str(snap['block_number']))==snap['block_hash'],'SNAPSHOT_NOT_CANONICAL')
        require(coverage.get('mechanism')=='PINNED_EVENT_RANGE_AND_ALL_INTENT_CORRELATION' and coverage.get('from_exclusive')==lo and coverage.get('to_inclusive')==hi,'COVERAGE_RANGE_OR_MECHANISM_UNKNOWN')
        require(coverage.get('pagination_complete') is True and coverage.get('ws_gaps')==[],'PAGINATION_OR_WS_GAP')
        require(coverage.get('unexplained_mutations')==[] and coverage.get('foreign_activity')==[],'FOREIGN_OR_UNEXPLAINED_MUTATION')
        require(type(expected_operator) is str and bool(expected_operator),'EXPECTED_OPERATOR_UNKNOWN')
        declaration=records['operator_declaration']
        require(declaration.get('owner')==expected_operator and declaration.get('declared_no_other_producers') is True and declaration.get('limitation')=='DECLARATION_NOT_PROOF_OTHER_KEYS_ABSENT','OTHER_PRODUCER_DECLARATION_UNKNOWN')
        # This is an explicit assumption plus bounded observed activity, never proof no other keys exist.
        require(coverage.get('other_producer_check')=='OBSERVED_WINDOW_ONLY','OTHER_PRODUCER_VERIFICATION_UNKNOWN')
        orders=local['orders']
        require(all(o['market']==market and o['token'] in tokens and baseline['observed_ms']<=o['send_intent_ms']<=closing['observed_ms'] for o in orders.values()),'LOCAL_INTENT_OUTSIDE_BOUNDED_SCOPE')
        known={o['order_id']:o for o in orders.values() if o['order_id']}
        require(unique(coverage['observed_order_ids'])==set(known),'FOREIGN_OR_MISSING_ORDER')
        fills=records['executions']['fills'];require(type(fills) is list and len(fills)<=1000,'FILL_LIST')
        receipt_rows=records['receipts']['receipts'];require(type(receipt_rows) is list and len(receipt_rows)<=1000,'RECEIPT_LIST')
        receipt_map={r['receipt']['transactionHash']:r for r in receipt_rows};require(len(receipt_map)==len(receipt_rows),'DUPLICATE_RECEIPT')
        from .bounded_acquisition import verify_native_bundle
        for deployment in records['executions'].get('deployments',{}).values():
            if deployment.get('applicability')=='FIXTURE_ONLY':
                require(all(bundle[k].get('fixture_only') is True for k in REQUIRED),'FIXTURE_DEPLOYMENT_NOT_LIVE_EVIDENCE')
        verify_native_bundle(local,records)
        cash=raw(baseline['cash_raw']);assets={t:raw(v) for t,v in baseline['assets_raw'].items()};seen=set();txs=set();cum={oid:Decimal(0) for oid in known};notionals={oid:0 for oid in known}
        totals={k:{'spent':Decimal(0),'cash_fee':Decimal(0),'share_fee':Decimal(0)} for k in local['reservations']}
        with localcontext() as ctx:
            ctx.prec=120
            for f in fills:
                tid=f['trade_id'];require(type(tid) is str and tid and tid not in seen,'DUPLICATE_FILL');seen.add(tid)
                require(f['order_id'] in known,'FOREIGN_FILL_ORDER');o=known[f['order_id']]
                require(all(f[k]==o[k] for k in ('market','token','side')) and f['market']==market and f['token'] in tokens,'FILL_INTENT_CONTEXT')
                require(f.get('native_effect_schema')=='EXPLICIT_NATIVE_CASH_SHARES/1' and f.get('cash_currency')=='pUSD' and f.get('asset_contract')==asset['asset_contract'],'NATIVE_FEE_EFFECTS_UNKNOWN')
                n,q,cf,sf=(raw(f[k]) for k in ('notional_raw','gross_shares_raw','cash_fee_raw','share_fee_raw'))
                require(q>0 and sf<=q,'FILL_NATIVE_AMOUNT')
                p=dec(f['price']);shares=Decimal(q)/1000000
                require(len(p.as_tuple().digits)<=100 and abs(p.as_tuple().exponent)<=100,'PRICE_PRECISION_UNSUPPORTED')
                require(0<p<1 and Fraction(p)*q==n,'NATIVE_NOTIONAL_ROUNDING_MAPPING_UNPROVEN')
                require((f['side']=='BUY' and p<=dec(o['price'])) or (f['side']=='SELL' and p>=dec(o['price'])),'FILL_PRICE_LIMIT')
                integer(f['exchange_ts_ms']);integer(f['receive_ts_ms']);integer(o['send_intent_ms'])
                require(baseline['observed_ms']<=o['send_intent_ms']<=f['exchange_ts_ms']<=f['receive_ts_ms']<=closing['observed_ms'],'FILL_TIME_WINDOW')
                tx=hashhex(f['transaction_hash']);require(tx in receipt_map,'MISSING_CANONICAL_RECEIPT');txs.add(tx)
                receipt=receipt_map[tx]['receipt'];require(f['receipt_digest']==digest(receipt),'FILL_RECEIPT_DIGEST')
                proof=f.get('native_effect_provenance',{})
                require(proof.get('kind')=='VERIFIED_EXCHANGE_NATIVE_EFFECT_DECODER' and type(proof.get('decoder_digest')) is str and re.fullmatch('[0-9a-f]{64}',proof['decoder_digest']) is not None,'NATIVE_EFFECT_DECODER_UNKNOWN')
                indices=proof.get('log_indices');require(type(indices) is list and indices and len(set(indices))==len(indices) and all(type(i) is int and i>=0 for i in indices),'NATIVE_EFFECT_LOG_LINKS')
                require(set(indices)<=set(int(l['logIndex'],16) for l in receipt['logs']),'NATIVE_EFFECT_LOG_MISSING')
                require(tid in local['fills'],'UNJOURNALED_FILL_REQUIRES_RECONCILIATION')
                lf=local['fills'][tid];require(lf['client_id']==o['client_id'],'LOCAL_FILL_CLIENT')
                for k in ('market','token','side','order_id'):require(lf['fill'][k]==f[k],'LOCAL_FILL_CONTEXT')
                for k,v in (('price',p),('shares',shares),('cash_fee',Decimal(cf)/1000000),('share_fee',Decimal(sf)/1000000)):require(dec(lf['fill'][k])==v,'LOCAL_NATIVE_EFFECT_DISAGREEMENT')
                if f['side']=='BUY':cash-=n+cf;assets[f['token']]+=q-sf
                else:cash+=n-cf;assets[f['token']]-=q+sf
                require(cash>=0 and assets[f['token']]>=0,'NEGATIVE_CASH_OR_ASSET')
                cum[f['order_id']]+=shares;notionals[f['order_id']]+=n
                op=totals[o['opportunity_id']];op['spent']+=Decimal(n)/1000000 if f['side']=='BUY' else 0;op['cash_fee']+=Decimal(cf)/1000000;op['share_fee']+=Decimal(sf)/1000000
        from .qualification import FeeRisk
        for key,total in totals.items():
            reservation=local['reservations'][key];require(total['spent']<=dec(reservation['notional']),'RESERVED_NOTIONAL_BREACH')
            risk_record=reservation.get('fee_risk')
            if risk_record is None:
                require(total['share_fee']==0,'SHARE_FEE_CONVERSION_UNKNOWN');equivalent=total['cash_fee']
            else:
                risk=FeeRisk(**risk_record);require(risk.market==market,'RESERVED_FEE_MARKET')
                require(total['cash_fee']<=dec(risk.cash_collateral) and total['share_fee']<=dec(risk.outcome_shares),'NATIVE_FEE_RESERVATION_BREACH')
                equivalent=risk.observed_cash(total['cash_fee'],total['share_fee'],now_ms)
                exact=Fraction(total['cash_fee'])+Fraction(total['share_fee'])*Fraction(dec(risk.collateral_per_share_upper or '0'))
                require(exact<=Fraction(dec(reservation['fee_ceiling'])),'EXACT_RESERVED_FEE_CEILING_BREACH')
            require(equivalent<=dec(reservation['fee_ceiling']),'RESERVED_FEE_CEILING_BREACH')
        require(seen==set(local['fills'])==unique(coverage['observed_trade_ids']),'TRADE_COVERAGE_DISAGREEMENT')
        require(txs==set(receipt_map),'UNATTRIBUTED_RECEIPT')
        for oid,o in known.items():
            require((o['side']=='BUY' and Decimal(notionals[oid])/1000000<=dec(o['notional'])) or (o['side']=='SELL' and cum[oid]<=dec(o['shares'])),'CUMULATIVE_ORDER_LIMIT')
        terminal=records['terminal_orders']['orders'];require(type(terminal) is list and len(terminal)==len(known),'TERMINAL_COVERAGE')
        terminal_ids=set()
        for t in terminal:
            oid=t['order_id'];require(oid in known and oid not in terminal_ids,'TERMINAL_ORDER_ID');terminal_ids.add(oid)
            integer(t['read_start_ms']);integer(t['observed_ms'])
            last_fill=max((f['receive_ts_ms'] for f in fills if f['order_id']==oid),default=known[oid]['send_intent_ms'])
            require(last_fill<=t['read_start_ms']<=t['observed_ms']<=closing['read_start_ms'] and now_ms-t['read_start_ms']<=5000,'TERMINAL_OBSERVATION_STALE_OR_BEFORE_FILL')
            require(t['status'] in ('FILLED','CANCELED','EXPIRED') and dec(t['cumulative_shares'])==cum[oid],'CUMULATIVE_OR_TERMINAL_UNKNOWN')
        require(cash==raw(closing['cash_raw']) and assets=={t:raw(v) for t,v in closing['assets_raw'].items()},'UNEXPLAINED_NATIVE_STATE_DELTA')
        cash_proof=dict(chain_id=137,wallet=D6,collateral_contract=CONTRACT,before={'block_number':lo,'block_hash':baseline['block_hash'],'balance_raw':baseline['cash_raw']},after={'block_number':hi,'block_hash':closing['block_hash'],'balance_raw':closing['cash_raw'],'observed_ms':closing['read_start_ms']},canonical_blocks=canonical,canonical_observed_ms=finality['read_start_ms'],receipts=receipt_rows)
        cash_check=reconcile_cash_delta(cash_proof,expected_wallet=D6,expected_contract=CONTRACT,expected_transactions=sorted(txs),now_ms=now_ms)
        require(cash_check['status']=='CASH_DELTA_MATCHED','RECEIPT_CASH_DELTA_UNPROVEN')
        delta=asset_receipt_deltas(receipt_rows,asset['asset_contract'],tokens)
        require(all(raw(baseline['assets_raw'][t])+delta[t]==assets[t] for t in tokens),'RECEIPT_ASSET_DELTA_UNPROVEN')
        out.update(native_cash_delta_check=cash_check,normalized_cash_raw=str(cash),normalized_assets_raw={k:str(v) for k,v in assets.items()},fills_count=len(seen),bounded_assumptions=['Verified scoped records and complete declared bounded event range','Human declaration does not exclude undisclosed producers or future activity'])
        if not out['blockers']:out['status']='BOUNDED_MATCH_UNDER_ASSUMPTIONS_NOT_FULL_WALLET'
    except Exception as exc:
        from .compare_accounts import safe_reason
        out['blockers'].append(safe_reason(exc))
    return out
