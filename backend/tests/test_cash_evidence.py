from copy import deepcopy
import pytest
from app.live.cash_evidence import reconcile_cash_delta,TRANSFER_TOPIC

W='0x'+'1'*40
C='0x'+'2'*40
OTHER='0x'+'3'*40
TX='0x'+'a'*64
H1='0x'+'b'*64
H2='0x'+'c'*64

def evidence():
    return dict(chain_id=137,wallet=W,collateral_contract=C,
        before=dict(block_number=10,block_hash=H1,balance_raw='109160000'),
        after=dict(block_number=11,block_hash=H2,balance_raw='104160000',observed_ms=1000),
        canonical_blocks={'10':H1,'11':H2},canonical_observed_ms=1000,
        receipts=[dict(observed_ms=1000,receipt=dict(status='0x1',transactionHash=TX,blockNumber='0xb',blockHash=H2,
            logs=[dict(address=C,topics=[TRANSFER_TOPIC,'0x'+'0'*24+W[2:],'0x'+'0'*24+OTHER[2:]],
                data='0x'+format(5000000,'064x'),transactionHash=TX,blockNumber='0xb',blockHash=H2,logIndex='0x0',removed=False)]))])

def assess(e,txs=None,now=1100):
    return reconcile_cash_delta(e,expected_wallet=W,expected_contract=C,expected_transactions=[TX] if txs is None else txs,now_ms=now)

def test_exact_base_units_do_not_invent_fees_or_pnl():
    r=assess(evidence())
    assert r['status']=='CASH_DELTA_MATCHED'
    assert r['delta_raw']=='-5000000' and r['after_balance_raw']=='104160000'
    assert r['fees_raw'] is None and r['pnl_raw'] is None
    assert not r['current_inventory_proven'] and not r['submit_allowed']

@pytest.mark.parametrize('kind',['wallet','contract','chain','reorg','failed','missing','duplicate','removed','foreign_tx','stale','future','balance','bad_units','data','truncated'])
def test_inconsistent_evidence_fails_closed(kind):
    e=evidence();r=e['receipts'][0]['receipt'];log=r['logs'][0]
    if kind=='wallet':e['wallet']=OTHER
    elif kind=='contract':e['collateral_contract']=OTHER
    elif kind=='chain':e['chain_id']=1
    elif kind=='reorg':e['canonical_blocks']['11']=H1
    elif kind=='failed':r['status']='0x0'
    elif kind=='missing':e['receipts']=[]
    elif kind=='duplicate':e['receipts'].append(deepcopy(e['receipts'][0]))
    elif kind=='removed':log['removed']=True
    elif kind=='foreign_tx':log['transactionHash']=H1
    elif kind=='stale':e['canonical_observed_ms']=599
    elif kind=='future':e['after']['observed_ms']=1101
    elif kind=='balance':e['after']['balance_raw']='104160001'
    elif kind=='bad_units':e['before']['balance_raw']=109.16
    elif kind=='data':log['data']='0x1'
    elif kind=='truncated':r['logs']=[]
    assert assess(e)['status']=='BLOCKED'


def test_self_transfer_has_zero_net_change():
    e=evidence();e['receipts'][0]['receipt']['logs'][0]['topics'][2]='0x'+'0'*24+W[2:]
    e['after']['balance_raw']=e['before']['balance_raw']
    assert assess(e)['delta_raw']=='0'


def test_logs_cannot_be_counted_twice():
    e=evidence();logs=e['receipts'][0]['receipt']['logs'];logs.append(deepcopy(logs[0]))
    e['after']['balance_raw']='99160000'
    assert assess(e)['status']=='BLOCKED'


def test_transaction_at_or_before_baseline_is_out_of_scope():
    e=evidence();e['receipts'][0]['receipt']['blockNumber']='0xa'
    assert assess(e)['status']=='BLOCKED'
