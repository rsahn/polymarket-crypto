import asyncio,copy,json,hashlib
import pytest
from .test_bounded_reconciliation import case,NOW,TX,H0,H1,EXCHANGE,REQUIRED
from .test_rpc_assembly import Response,URL
from .rpc_assembly import assemble
from .concrete_readers import PinnedEvidenceAuthority
from .native_v2 import COMMIT
from .core import digest

def setup(case):
    b=copy.deepcopy(case[1]);records={k:b[k] for k in REQUIRED}
    for r in records.values():r['provider_identity']='fixture-provider'
    artifact=dict(origin='fixture://independent-test-build',source_commit=COMMIT,chain_id=137,exchange=EXCHANGE,kind='EXACT_NONPROXY_RUNTIME',unresolved_immutables=[],runtime_code='0x6000',runtime_sha256=hashlib.sha256(bytes.fromhex('6000')).hexdigest(),source_contents={'fixture.sol':'synthetic'},build_provenance=dict(compiler_version='0.8.30',compiler_settings={'fixture':True},source_sha256={'fixture.sol':hashlib.sha256(b'synthetic').hexdigest()},dependencies={},libraries={},constructor_immutables={}),fixture_only=True)
    receipt=b['receipts']['payload']['receipts'][0]['receipt']
    class C:
        def __init__(self,*a,**k):pass
        def request(self,method,path,body,headers):self.r=json.loads(body)
        def getresponse(self):
            r=self.r;m=r['method'];p=r['params']
            if m=='eth_chainId':v='0x89'
            elif m=='eth_getCode':v='0x6000'
            elif m=='eth_getTransactionReceipt':v=receipt
            elif m=='eth_getBlockByNumber':v=dict(number=p[0],hash={100:H0,101:H1}[int(p[0],16)])
            elif m=='eth_call':
                n=int(p[1],16);data=p[0]['data']
                v='0x'+format((100000000 if n==100 else 98990000) if data.startswith('0x70a08231') else (2000000 if n==101 and int(data[-64:],16)==123 else 0),'064x')
            else:raise AssertionError(m)
            return Response(json.dumps(dict(jsonrpc='2.0',id=r['id'],result=v)).encode())
        def close(self):pass
    kwargs=dict(endpoint=URL,approved_endpoint=URL,transactions=[TX],blocks={100:H0,101:H1},context={'market':b['market'],'tokens':b['tokens']},source_records=records,expected_operator='FICTIONAL_TEST_OPERATOR',clock=lambda:NOW,deadline_ms=NOW+5000,max_calls=40,artifacts={TX:artifact},trusted_manifests={artifact['origin']:digest(artifact)},connection_factory=C,reader_plan=dict(baseline_block=100,closing_block=101),provider_identity='fixture-provider',fixture_only=True)
    pins={(k,'source'):r['source_digest'] for k,r in records.items()}
    pins.update({(k,'result'):r['source_digest'] for k,r in records.items()})
    return kwargs,pins

def run(case,kwargs,pins):return asyncio.run(assemble(case[0],source_authority=PinnedEvidenceAuthority('fixture-provider',pins,fixture_only=True),**kwargs))

def approved_fixture(case):
    kwargs,pins=setup(case)
    # First unapproved output is rejected by the REAL authority. Test reviews exact
    # deterministic fixture outputs then supplies separate explicit result pins.
    preview=run(case,kwargs,pins)
    assert not preview['result']['verdict']['status'].startswith('BOUNDED_MATCH')
    bundle=preview['result']['bundle']
    for k in REQUIRED:pins[(k,'result')]=digest(bundle[k]['payload'])
    return kwargs,pins

def test_actual_reader_plan_authority_and_historical_baseline(case):
    kwargs,pins=approved_fixture(case);original=copy.deepcopy(kwargs['source_records']['baseline'])
    out=run(case,kwargs,pins)
    assert out['result']['verdict']['status'].startswith('BOUNDED_MATCH'),out['result']['verdict']
    assert out['result']['bundle']['baseline']==original
    assert out['observations']['baseline_corroboration']['read_start_ms']==NOW>original['payload']['observed_ms']
    assert out['result']['verdict']['local_intent_count']>0

@pytest.mark.parametrize('mutation',['source_only','result_only','wrong_role','unapproved_result','altered_baseline','late_baseline'])
def test_role_pins_and_baseline_fail_closed(case,mutation):
    kwargs,pins=approved_fixture(case)
    if mutation=='source_only':pins.pop(('finality','result'))
    if mutation=='result_only':pins.pop(('finality','source'))
    if mutation=='wrong_role':pins[('finality','source')]=pins[('finality','result')]
    if mutation=='unapproved_result':pins[('finality','result')]='0'*64
    if mutation in ('altered_baseline','late_baseline'):
        r=kwargs['source_records']['baseline'];r['payload']['cash_raw']='1' if mutation=='altered_baseline' else r['payload']['cash_raw']
        if mutation=='late_baseline':r['payload']['observed_ms']=NOW
        r['source_digest']=digest(r['payload'])
        if mutation=='late_baseline':pins[('baseline','source')]=r['source_digest']
    out=run(case,kwargs,pins);assert not out['result']['verdict']['status'].startswith('BOUNDED_MATCH')

def test_authenticated_baseline_cannot_disagree_with_later_corroboration(case):
    kwargs,pins=approved_fixture(case);r=kwargs['source_records']['baseline']
    r['payload']['cash_raw']='99999999';r['source_digest']=digest(r['payload'])
    pins[('baseline','source')]=r['source_digest'];pins[('baseline','result')]=r['source_digest']
    out=run(case,kwargs,pins)
    assert 'BASELINE_CORROBORATION_MISMATCH' in out['result']['verdict']['blockers']
