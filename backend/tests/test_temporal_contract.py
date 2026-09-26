import asyncio
import pytest
from app.live.temporal_contract import assess_domains, domain_policy


def observations():
    return dict(account=dict(available=True,authenticated=True,observed_ms=1000,complete=True,pagination_complete=True,reconciled=True,balance_usdc='100',allowance_usdc='100',open_order_ids=[]),
        positions=dict(available=True,observed_ms=1000,complete=True,balances={}),
        book=dict(available=True,connected=True,synchronized=True,fresh=True,book_synced=True,observed_ms=1900),
        risk=dict(available=True,observed_ms=1000,allow=True,reconciled=True,fees_complete=True,exposure_known=True,no_unresolved_execution=True),
        geo=dict(available=True,blocked=False,observed_ms=1000),
        signal=dict(available=True,valid=True,source_ms=1800,received_ms=1850,observed_ms=1900))


def assess(v=None):
    return assess_domains(v or observations(),now=2000,local=dict(phase='CLOSED',integrity_verified=True,last_hash='a'*64),
        generation=dict(id=1,ledger_hash='a'*64,watermark=dict(block_number=1,block_hash='b'*64),
            components={n:dict(generation=1,complete=True,observed_ms=1000) for n in ('balance','orders','trades','positions','inventory')}),collateral_unit='USDC')


def test_book_stale_account_observation_independently_valid():
    v=observations();v['book']['observed_ms']=1000
    d=assess(v)
    assert d['book']['reason']=='BOOK_STALE'
    assert d['authentication']['observation_valid']
    assert d['balance']['observation_valid']
    assert d['balance']['age_ms']==1000
    assert d['balance']['calibration']=='UNCALIBRATED'
    assert not d['balance']['ready']


def test_old_account_not_book_staleness():
    d=assess()
    assert d['book']['observation_valid']
    assert d['balance']['reason']=='BALANCE_UNCALIBRATED'
    assert d['balance']['limit_ms'] is None


@pytest.mark.parametrize('component,field,value,domain,reason',[
    ('account','authenticated',False,'authentication','AUTHENTICATION_INVALID'),
    ('account','open_order_ids',None,'orders','OPEN_ORDER_STATE_UNCERTAIN'),
    ('positions','balances',{'t':'1'},'positions','POSITION_STATE_UNCERTAIN'),
    ('risk','reconciled',False,'session_risk','SESSION_RISK_UNRECONCILED'),
    ('signal','observed_ms',1000,'signal','SIGNAL_STALE'),
])
def test_independent_evidence_failures(component,field,value,domain,reason):
    assert assess()[domain]['observation_valid']
    v=observations();v[component][field]=value;d=assess(v)
    assert d[domain]['reason']==reason and not d[domain]['ready']
    assert d['book']['observation_valid']


def test_canonical_inventory_is_never_current_by_age():
    for age in (0,501,1301,60000):
        v=observations();v['positions'].update(observed_ms=2000-age,current_inventory_proven=True)
        d=assess(v)
        assert d['inventory']['reason']=='INVENTORY_UNPROVEN'
        assert not d['inventory']['ready']


def test_unknown_domains_have_no_invented_sla():
    assert domain_policy('book')['limit_ms']==500
    assert domain_policy('balance')['limit_ms'] is None
    assert domain_policy('signal')['calibration']=='CONSERVATIVE_EXISTING_POLICY'


def test_no_legacy_global_override_changes_book():
    from app.live.freshness_policy import freshness_policy
    from app.live.production_readonly import BookStateSource
    with freshness_policy(1300):
        b=BookStateSource(clock=lambda:2000);b.connect('m',('a','b'),1)
        with pytest.raises(ValueError,match='STALE_BOOK'):b.update('a',[(.4,2)],[(.5,2)],1000,1)


def test_ready_requires_calibration_and_durable_recovery():
    from app.live.readiness import ProductionReadinessCheck
    from app.live.forward_readiness import ObservationSource
    v=observations()
    r=asyncio.run(ProductionReadinessCheck(**{k:ObservationSource(v[k]) for k in ('account','positions','book','risk','geo')},
        local_reader=lambda:{'phase':'CLOSED'},clock=lambda:2000).run())
    assert not r['SYSTEM_READY'] and not r['ready_for_arm'] and not r['submit_allowed']
    assert r['domain_details']['recovery']['reason']=='RECOVERY_STATE_INVALID'
    assert r['domain_details']['balance']['calibration']=='UNCALIBRATED'


def test_generation_identity_binds_reconciliation_to_durable_ledger():
    from app.live.temporal_contract import generation_structure
    g=dict(id=1,ledger_hash='b'*64,watermark=dict(block_number=1,block_hash='c'*64),
        components={n:dict(generation=1,complete=True,observed_ms=1000) for n in ('balance','orders','trades','positions','inventory')})
    assert generation_structure(g,2000,'b'*64)['complete']
    assert not generation_structure(g,2000,'a'*64)['complete']
    g['components']['orders']['generation']=True
    assert not generation_structure(g,2000,'b'*64)['complete']
