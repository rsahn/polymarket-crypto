import copy,pytest,asyncio
from .test_bounded_reconciliation import case,ORDER,D6,TX,EXCHANGE,OTHER,word,topic,reseal,FixtureAuthority,NOW
from .native_v2 import decode,FILLED,MATCHED,BATCH
from .bounded_acquisition import acquire
from .bounded_reconciliation import REQUIRED

def args(case):
    b=case[1];return dict(receipt=copy.deepcopy(b['receipts']['payload']['receipts'][0]['receipt']),account=D6,intents={ORDER:dict(account=D6,side='BUY',token='123',order_id=ORDER,client_id='client')},deployment=b['executions']['payload']['deployments'][TX])
def test_native_buy_fee_is_cash_not_shares(case):
    r=decode(**args(case));assert r['cash_delta_raw']=='-1010000' and r['fills'][0]['share_fee_raw']=='0' and r['fills'][0]['role']=='MAKER'
@pytest.mark.parametrize('mutation',['topic','length','side','padding','removed','reorg','foreign_order','foreign_account','foreign_token','duplicate','fee','shares','wrong_address','unknown_version','unproven','batch_duplicate','overflow'])
def test_bad_native_abi_or_attribution_blocks(case,mutation):
    a=args(case);r=a['receipt'];l=r['logs'][2]
    if mutation=='topic':l['topics'][0]='0x'+'0'*64
    if mutation=='length':l['data']+='00'
    if mutation=='side':l['data']='0x'+word(2)+l['data'][66:]
    if mutation=='padding':l['topics'][2]='0x'+'1'*64
    if mutation=='removed':l['removed']=True
    if mutation=='reorg':l['blockHash']='0x'+'1'*64
    if mutation=='foreign_order':l['topics'][1]='0x'+'1'*64
    if mutation=='foreign_account':l['topics'][2]=topic(OTHER)
    if mutation=='foreign_token':l['data']='0x'+word(0)+word(999)+l['data'][130:]
    if mutation=='duplicate':r['logs'].append(copy.deepcopy(l))
    if mutation=='fee':l['data']='0x'+''.join(word(v) for v in [0,123,1000000,2000000,999,0,0])
    if mutation=='shares':r['logs'][1]['data']='0x'+word(123)+word(1999000)
    if mutation=='wrong_address':l['address']=OTHER
    if mutation=='unknown_version':a['deployment']={**a['deployment'],'version':'V1'}
    if mutation=='unproven':a['deployment']={**a['deployment'],'applicability':'UNKNOWN'}
    if mutation=='batch_duplicate':r['logs'][1].update(topics=[BATCH,*r['logs'][1]['topics'][1:]],data='0x'+''.join(word(v) for v in [64,160,2,123,123,2,1000000,1000000]))
    if mutation=='overflow':l['data']='0x'+word(2**256)+l['data'][66:]
    with pytest.raises(ValueError):decode(**a)
def test_taker_summary_is_not_double_counted(case):
    a=args(case);l=a['receipt']['logs'][2];l['topics'][3]=topic(EXCHANGE)
    a['receipt']['logs'].append({**l,'logIndex':'0x3','topics':[MATCHED,ORDER,topic(D6)],'data':'0x'+''.join(word(v) for v in [0,123,1000000,2000000])})
    r=decode(**a);assert len(r['fills'])==1 and r['fills'][0]['role']=='TAKER'
def test_batch_transfers_supported(case):
    a=args(case);l=a['receipt']['logs'][1];l.update(topics=[BATCH,*l['topics'][1:]],data='0x'+''.join(word(v) for v in [64,128,1,123,1,2000000]))
    assert decode(**a)['asset_deltas_raw']=={'123':'2000000'}
def test_complementary_counterparty_event_not_double_counted(case):
    a=args(case);l=a['receipt']['logs'][2]
    a['receipt']['logs'].append({**l,'logIndex':'0x3','topics':[FILLED,'0x'+'5'*64,topic(OTHER),topic(D6)],'data':'0x'+''.join(word(v) for v in [1,123,2000000,1000000,0,0,0])})
    assert len(decode(**a)['fills'])==1
def test_bridge_only_explicit_providers_and_preserves_unknown_coverage(case):
    async def run():
        b=case[1];calls=[]
        def provider(k):
            def read(ctx):calls.append(k);return copy.deepcopy(b[k])
            return read
        providers={k:provider(k) for k in REQUIRED};ctx=dict(market=b['market'],tokens=b['tokens'])
        with pytest.raises(ValueError,match='NOT_AUTHORIZED'):await acquire(case[0],providers=providers,authorized_kinds=[],context=ctx,authority=FixtureAuthority(),clock=lambda:NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
        assert calls==[]
        r=await acquire(case[0],providers=providers,authorized_kinds=REQUIRED,context=ctx,authority=FixtureAuthority(),clock=lambda:NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
        assert r['verdict']['status'].startswith('BOUNDED_MATCH')
        b['coverage']['payload']['pagination_complete']=None;reseal(b)
        r=await acquire(case[0],providers=providers,authorized_kinds=REQUIRED,context=ctx,authority=FixtureAuthority(),clock=lambda:NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
        assert r['verdict']['blockers']

    asyncio.run(run())

def test_roundtrip_netting_uses_two_native_fee_events_not_aggregate_allocation(case):
    a=args(case);r=a['receipt'];sell='0x'+'6'*64
    a['intents'][sell]=dict(account=D6,side='SELL',token='123',order_id=sell,client_id='sell')
    base=r['logs'][2]
    r['logs'].append({**base,'logIndex':'0x3','topics':[FILLED,sell,topic(D6),topic(OTHER)],'data':'0x'+''.join(word(v) for v in [1,123,2000000,1000000,1000,0,0])})
    r['logs'].append({**r['logs'][0],'logIndex':'0x4','topics':[r['logs'][0]['topics'][0],topic(OTHER),topic(D6)],'data':'0x'+word(999000)})
    r['logs'].append({**r['logs'][1],'logIndex':'0x5','topics':[r['logs'][1]['topics'][0],topic(OTHER),topic(D6),topic(OTHER)]})
    d=decode(**a);assert len(d['fills'])==2 and d['cash_delta_raw']=='-11000' and d['asset_deltas_raw']=={'123':'0'}

def test_signed_claimed_effect_cannot_replace_actual_event(case):
    from .test_bounded_reconciliation import evaluate_case
    b=copy.deepcopy(case[1]);f=b['executions']['payload']['fills'][0];f['cash_fee_raw']='9999'
    assert 'DECODED_EFFECT_DISAGREEMENT' in evaluate_case(case,b)['blockers']

def test_fixture_deployment_never_silently_live(case):
    from .bounded_reconciliation import evaluate
    b=copy.deepcopy(case[1])
    for k in REQUIRED:b[k].pop('fixture_only')
    class TrustAll:
        def verify(self,r):return True
    r=evaluate(case[0],b,authority=TrustAll(),now_ms=NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
    assert 'FIXTURE_DEPLOYMENT_NOT_LIVE_EVIDENCE' in r['blockers']
