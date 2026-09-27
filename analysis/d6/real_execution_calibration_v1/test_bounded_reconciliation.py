import copy
import pytest
from eth_utils import keccak
from .bounded_reconciliation import *
from .core import Journal,CalibrationLedger
from .qualification import FeeRisk
from .adapters import AccountAdapter
from app.live.cash_evidence import TRANSFER_TOPIC
from .native_v2 import FILLED,SCHEMA as NATIVE_SCHEMA,COMMIT
EXCHANGE='0xE111180000d2663C0091e4f400237545B87B996B'
ORDER='0x'+'7'*64
SELL_ORDER='0x'+'6'*64
def native_data(side,n,q,f):return '0x'+''.join(word(v) for v in ([0,123,n,q,f,0,0] if side=='BUY' else [1,123,q,n,f,0,0]))

NOW=100010;MARKET='0x'+'a'*64;ASSET='0x4D97DCd97eC945f40cF65F87097ACe5EA0476045';OTHER='0x'+'c'*40;TX='0x'+'d'*64
H0='0x'+'0'*63+'1';H1='0x'+'0'*63+'2'
def word(n):return format(n,'064x')
def topic(a):return '0x'+a[2:].rjust(64,'0')
class FixtureAuthority:
    def verify(self,r):return r.get('fixture_only') is True and r['source_digest']==digest(r['payload'])
def record(kind,p):return dict(kind=kind,chain_id=137,scope=SCOPE,account=D6,experiment='fixture-experiment',payload=p,source_digest=digest(p),fixture_only=True)
def reseal(b):
    for k in REQUIRED:b[k]['source_digest']=digest(b[k]['payload'])
    return b

@pytest.fixture
def case(tmp_path):
    path=tmp_path/'journal.jsonl';j=Journal(path,'fixture-experiment');ledger=CalibrationLedger(j,D6,'100')
    # Explicit offline fixture state; the new bounded evaluator never sets this gate.
    ledger.reconciled=True;ledger.seal_shadow('op',{'token':'123','market':MARKET})
    risk=FeeRisk('1','0.01','1','f'*64,MARKET,200000,'FIXTURE_ONLY')
    ledger.reserve('op','1','1',risk);ledger.intent('client','BUY','123',MARKET,'0.5','2','1',{},90000)
    ledger.ack('client',{'ok':True,'order_id':ORDER},90001)
    fill=dict(trade_id='trade',order_id=ORDER,token='123',market=MARKET,side='BUY',price='0.5',shares='2',cash_fee='0.01',share_fee='0',fee_evidence={'cash_effect_proven':True,'share_effect_proven':True},exchange_ts_ms=91000,receive_ts_ms=99980)
    assert ledger.fill('client',fill);assert ledger.terminal('client','FILLED','2');j.close()
    def log(index,address,topics,data):return dict(address=address,topics=topics,data=data,logIndex=hex(index),blockNumber=hex(101),blockHash=H1,transactionHash=TX,removed=False)
    receipt=dict(transactionHash=TX,blockNumber=hex(101),blockHash=H1,status='0x1',logs=[
        log(0,CONTRACT,[TRANSFER_TOPIC,topic(D6),topic(OTHER)],'0x'+word(1010000)),
        log(1,ASSET,['0x'+keccak(text='TransferSingle(address,address,address,uint256,uint256)').hex(),topic(OTHER),topic(OTHER),topic(D6)],'0x'+word(123)+word(2000000)),
        log(2,EXCHANGE,[FILLED,ORDER,topic(D6),topic(OTHER)],native_data('BUY',1000000,2000000,10000))]) # synthetic native-fee event, NOT a production ABI
    baseline=dict(chain_id=137,collateral_symbol='pUSD',collateral_decimals=6,collateral_contract=CONTRACT,asset_contract=ASSET,cash_raw='100000000',assets_raw={'123':'0','456':'0'},block_number=100,block_hash=H0,read_start_ms=79990,observed_ms=80000)
    closing={**baseline,'cash_raw':'98990000','assets_raw':{'123':'2000000','456':'0'},'block_number':101,'block_hash':H1,'read_start_ms':99990,'observed_ms':100000}
    native={**fill,'native_effect_schema':'EXPLICIT_NATIVE_CASH_SHARES/1','cash_currency':'pUSD','asset_contract':ASSET,'notional_raw':'1000000','gross_shares_raw':'2000000','cash_fee_raw':'10000','share_fee_raw':'0','transaction_hash':TX,'receipt_digest':digest(receipt),'native_effect_provenance':{'kind':'VERIFIED_EXCHANGE_NATIVE_EFFECT_DECODER','decoder_digest':'f'*64,'log_indices':[2]}}
    payloads=dict(baseline=baseline,closing=closing,asset_mapping={'market':MARKET,'tokens':['123','456'],'asset_contract':ASSET,'share_decimals':6},coverage={'mechanism':'PINNED_EVENT_RANGE_AND_ALL_INTENT_CORRELATION','from_exclusive':100,'to_inclusive':101,'pagination_complete':True,'ws_gaps':[],'unexplained_mutations':[],'foreign_activity':[],'other_producer_check':'OBSERVED_WINDOW_ONLY','observed_order_ids':[ORDER],'observed_trade_ids':['trade']},finality={'policy':'PROVIDER_FINALIZED_PLUS_HASH_RECHECK','finalized_number':101,'read_start_ms':99990,'observed_ms':100005,'recheck_read_start_ms':100001,'canonical_hashes':{'100':H0,'101':H1},'rechecked_hashes':{'100':H0,'101':H1}},executions={'fills':[native],'order_hash_bindings':{ORDER:'client'},'deployments':{TX:dict(version=NATIVE_SCHEMA,source_commit=COMMIT,chain_id=137,exchange=EXCHANGE,collateral=CONTRACT,asset=ASSET,applicability='FIXTURE_ONLY')}},terminal_orders={'orders':[{'order_id':ORDER,'status':'FILLED','cumulative_shares':'2','read_start_ms':99985,'observed_ms':99989}]},receipts={'receipts':[{'observed_ms':99990,'receipt':receipt}]},operator_declaration={'owner':'FICTIONAL_TEST_OPERATOR','declared_no_other_producers':True,'limitation':'DECLARATION_NOT_PROOF_OTHER_KEYS_ABSENT'})
    b=dict(schema=SCHEMA,scope=SCOPE,tokens=['123','456'],market=MARKET,**{k:record(k,v) for k,v in payloads.items()})
    return path,b,ledger

def evaluate_case(case,b=None,authority=True):
    path,original,_=case
    return evaluate(path,reseal(b or copy.deepcopy(original)),authority=FixtureAuthority() if authority else None,now_ms=NOW,expected_operator='FICTIONAL_TEST_OPERATOR')

def test_scoped_match_reuses_journal_and_cash_decoder_without_promoting_ledger(case):
    before=case[2].reconciled;r=evaluate_case(case)
    assert r['status']=='BOUNDED_MATCH_UNDER_ASSUMPTIONS_NOT_FULL_WALLET',r
    assert r['normalized_cash_raw']=='98990000' and r['normalized_assets_raw']['123']=='2000000'
    assert case[2].reconciled==before==False and not r['full_wallet_atomicity_proven'] and not r['submit_allowed'] and r['STOP_NEW_ENTRIES']
    import types
    adapter=AccountAdapter(None,None,account=D6,collateral=CONTRACT,authority=types.SimpleNamespace(verify=lambda record:True),session='fixture-experiment')
    with pytest.raises(ValueError,match='PARTIAL_SCOPE'):adapter.normalize_snapshot(r)

def test_no_actual_producer_proofs_remains_unknown(case):
    r=evaluate_case(case,authority=False)
    assert r['status']=='UNKNOWN_CUSTODY_REQUIRED' and 'VERIFIED_BOUNDED_RECORDS_UNAVAILABLE' in r['blockers']

@pytest.mark.parametrize('mutation',['reorg','not_final','ws_gap','pagination','foreign_order','foreign_trade','unexplained','stale_closing','unknown_terminal','cumulative','missing_receipt','missing_asset_log','missing_native_decoder','fee_unknown','wrong_currency','missing_operator','claim_exclusivity','wrong_assets','foreign_token','duplicate_fill','native_rounding','source_digest'])
def test_adversarial_bounded_states_require_custody(case,mutation):
    b=copy.deepcopy(case[1]);p=lambda k:b[k]['payload'];f=p('executions')['fills'][0]
    if mutation=='reorg':p('finality')['rechecked_hashes']['101']=H0
    if mutation=='not_final':p('finality')['finalized_number']=100
    if mutation=='ws_gap':p('coverage')['ws_gaps']=['gap']
    if mutation=='pagination':p('coverage')['pagination_complete']=False
    if mutation=='foreign_order':p('coverage')['observed_order_ids'].append('foreign')
    if mutation=='foreign_trade':p('coverage')['observed_trade_ids'].append('foreign')
    if mutation=='unexplained':p('coverage')['unexplained_mutations']=['unexplained-transfer']
    if mutation=='stale_closing':p('closing')['read_start_ms']=90000
    if mutation=='unknown_terminal':p('terminal_orders')['orders'][0]['status']='MATCHED'
    if mutation=='cumulative':p('terminal_orders')['orders'][0]['cumulative_shares']='1'
    if mutation=='missing_receipt':p('receipts')['receipts']=[]
    if mutation=='missing_asset_log':
        rr=p('receipts')['receipts'][0]['receipt'];rr['logs']=[rr['logs'][0],rr['logs'][2]];f['receipt_digest']=digest(rr)
    if mutation=='missing_native_decoder':f.pop('native_effect_provenance')
    if mutation=='fee_unknown':f['cash_fee_raw']=None;f['status']='CONFIRMED'
    if mutation=='wrong_currency':f['cash_currency']='USDC'
    if mutation=='missing_operator':p('operator_declaration')['declared_no_other_producers']=None
    if mutation=='claim_exclusivity':p('operator_declaration')['limitation']='ALL_OTHER_KEYS_PROVEN_ABSENT'
    if mutation=='wrong_assets':p('baseline')['assets_raw'].pop('456')
    if mutation=='foreign_token':f['token']='999'
    if mutation=='duplicate_fill':p('executions')['fills'].append(copy.deepcopy(f))
    if mutation=='native_rounding':f['price']='0.4999999'
    if mutation=='source_digest':
        b['closing']['source_digest']='e'*64;r=evaluate(case[0],b,authority=FixtureAuthority(),now_ms=NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
    else:r=evaluate_case(case,b)
    assert r['status']=='UNKNOWN_CUSTODY_REQUIRED' and r['blockers'] and not r['calibration_ready'],r

def test_unacknowledged_intent_never_disappears_when_orders_empty(tmp_path):
    path=tmp_path/'unknown';j=Journal(path,'fixture-experiment');ledger=CalibrationLedger(j,D6,'100');ledger.reconciled=True
    ledger.seal_shadow('op',{'token':'123','market':MARKET});ledger.reserve('op','1','1');ledger.intent('lost','BUY','123',MARKET,'0.5','2','1',{},90000);j.close()
    r=evaluate(path,now_ms=NOW)
    assert r['unknown_local_intents']==['lost'] and r['custody_review_required']

def test_corrupt_journal_does_not_supply_a_baseline(case):
    path=case[0];data=path.read_bytes();path.write_bytes(data.replace(b'100',b'101',1))
    r=evaluate(path,case[1],authority=FixtureAuthority(),now_ms=NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
    assert r['status']=='UNKNOWN_CUSTODY_REQUIRED' and r['blockers']

def start_fixture_ledger(path,share_risk='0.01'):
    j=Journal(path,'fixture-experiment');l=CalibrationLedger(j,D6,'100');l.reconciled=True
    l.seal_shadow('op',{'token':'123','market':MARKET})
    l.reserve('op','1','1',FeeRisk('1',share_risk,'1','f'*64,MARKET,200000,'FIXTURE_ONLY'))
    l.intent('client','BUY','123',MARKET,'0.5','2','1',{},90000);l.ack('client',{'ok':True,'order_id':ORDER},90001)
    return j,l

def test_multiple_partial_native_fills_sum_to_terminal_and_receipt(case,tmp_path):
    b=copy.deepcopy(case[1]);original=case[2].fills;path=tmp_path/'partials'
    j,l=start_fixture_ledger(path);native=b['executions']['payload']['fills'][0]
    rr=b['receipts']['payload']['receipts'][0]['receipt'];rr['logs'][2]['data']=native_data('BUY',500000,1000000,5000)
    rr['logs'].append({**rr['logs'][2],'logIndex':'0x3'})
    fills=[]
    for i in (1,2):
        f={**native,'trade_id':'part'+str(i),'shares':'1','cash_fee':'0.005','share_fee':'0','notional_raw':'500000','gross_shares_raw':'1000000','cash_fee_raw':'5000','share_fee_raw':'0','exchange_ts_ms':91000+i,'receive_ts_ms':99970+i,'receipt_digest':digest(rr),'native_effect_provenance':{'kind':'VERIFIED_EXCHANGE_NATIVE_EFFECT_DECODER','decoder_digest':'f'*64,'log_indices':[i+1]}}
        assert l.fill('client',f);fills.append(f)
    assert l.terminal('client','FILLED','2');j.close()
    b['executions']['payload']['fills']=fills;b['coverage']['payload']['observed_trade_ids']=['part1','part2']
    r=evaluate(path,reseal(b),authority=FixtureAuthority(),now_ms=NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
    assert r['status']=='BOUNDED_MATCH_UNDER_ASSUMPTIONS_NOT_FULL_WALLET' and r['fills_count']==2,r

def test_buy_sell_roundtrip_native_accounting_does_not_enable_entries(case,tmp_path):
    b=copy.deepcopy(case[1]);buy=copy.deepcopy(b['executions']['payload']['fills'][0]);path=tmp_path/'roundtrip'
    j,l=start_fixture_ledger(path,'0');assert l.fill('client',buy);assert l.terminal('client','FILLED','2')
    l.reconciled=True  # explicit fixture setup, not a result of the bounded evaluator
    l.intent('sell-client','SELL','123',MARKET,'0.5','2','1',{},99981);l.ack('sell-client',{'ok':True,'order_id':SELL_ORDER},99982)
    tx2='0x'+'9'*64;h2='0x'+'8'*64;rr=copy.deepcopy(b['receipts']['payload']['receipts'][0]['receipt'])
    rr.update(transactionHash=tx2,blockNumber=hex(102),blockHash=h2)
    for event in rr['logs']:event.update(transactionHash=tx2,blockNumber=hex(102),blockHash=h2)
    rr['logs'][0].update(topics=[TRANSFER_TOPIC,topic(OTHER),topic(D6)],data='0x'+word(999000))
    rr['logs'][1]['topics'][2:]=[topic(D6),topic(OTHER)]
    rr['logs'][2]['data']=native_data('SELL',1000000,2000000,1000);rr['logs'][2]['topics'][1]=SELL_ORDER
    sell={**buy,'trade_id':'sell-trade','order_id':SELL_ORDER,'side':'SELL','shares':'2','cash_fee':'0.001','share_fee':'0','notional_raw':'1000000','gross_shares_raw':'2000000','cash_fee_raw':'1000','share_fee_raw':'0','exchange_ts_ms':99983,'receive_ts_ms':99986,'transaction_hash':tx2,'receipt_digest':digest(rr)}
    assert l.fill('sell-client',sell);assert l.terminal('sell-client','FILLED','2');j.close()
    b['executions']['payload']['order_hash_bindings'][SELL_ORDER]='sell-client';b['executions']['payload']['deployments'][tx2]=b['executions']['payload']['deployments'][TX];b['executions']['payload']['fills'].append(sell);b['receipts']['payload']['receipts'].append({'observed_ms':99990,'receipt':rr})
    c=b['closing']['payload'];c.update(cash_raw='99989000',assets_raw={'123':'0','456':'0'},block_number=102,block_hash=h2,read_start_ms=99998)
    cv=b['coverage']['payload'];cv.update(to_inclusive=102,observed_order_ids=[ORDER,SELL_ORDER],observed_trade_ids=['trade','sell-trade'])
    f=b['finality']['payload'];f['finalized_number']=102;f['canonical_hashes']['102']=h2;f['rechecked_hashes']['102']=h2
    b['terminal_orders']['payload']['orders'].append({'order_id':SELL_ORDER,'status':'FILLED','cumulative_shares':'2','read_start_ms':99990,'observed_ms':99991})
    r=evaluate(path,reseal(b),authority=FixtureAuthority(),now_ms=NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
    assert r['status']=='BOUNDED_MATCH_UNDER_ASSUMPTIONS_NOT_FULL_WALLET' and r['normalized_assets_raw']=={'123':'0','456':'0'},r
    assert r['STOP_NEW_ENTRIES'] and not r['calibration_ready'] and not l.reconciled

def test_fee_reservation_breach_not_hidden_by_matching_cash(case):
    import json
    path=case[0];rows=list(Journal.read(path));previous='0'*64
    for row in rows:
        row.pop('hash');row['previous']=previous
        if row['kind']=='RESERVE':row['payload']['fee_risk']['cash_collateral']='0.001'
        row['hash']=digest(row);previous=row['hash']
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    r=evaluate_case(case)
    assert 'NATIVE_FEE_RESERVATION_BREACH' in r['blockers'] and not r['calibration_ready']

def test_sealed_shadow_identity_cannot_be_replaced_by_another_allowed_token(case):
    import json
    path=case[0];rows=list(Journal.read(path));previous='0'*64
    for row in rows:
        row.pop('hash');row['previous']=previous
        if row['kind']=='DURABLE_INTENT':row['payload']['token']='456'
        row['hash']=digest(row);previous=row['hash']
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    r=evaluate_case(case)
    assert 'SEALED_INTENT_IDENTITY' in r['blockers'] and not r['submit_allowed']
