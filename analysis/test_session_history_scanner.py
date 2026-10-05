"""Adversarial scanner tests; fixtures are never production evidence."""
import pytest
from analysis.scan_deposit_session_history import decode, scan, EVENTS, RPC, WALLET

def event(kind='authorized'):
    topic=next(k for k,v in EVENTS.items() if v==kind)
    return dict(address=WALLET,topics=[topic,'0x'+'0'*24+'1'*40],
        data='0x'+format(123,'064x') if kind=='authorized' else '0x',
        blockNumber='0xa',blockHash='0x'+'2'*64,transactionHash='0x'+'3'*64,
        transactionIndex='0x0',logIndex='0x1',removed=False)

@pytest.mark.parametrize('kind',list(EVENTS.values()))
def test_event_decodes(kind):
    result=decode(event(kind));assert result['kind']==kind
    assert result['signer']=='0x'+'1'*40
    assert result['valid_until']==(123 if kind=='authorized' else None)

@pytest.mark.parametrize('mutation',['missing_signer','bad_padding','missing_expiry'])
def test_event_rejects_incomplete(mutation):
    row=event()
    if mutation=='missing_signer':row['topics'].pop()
    if mutation=='bad_padding':row['topics'][1]='0x'+'1'*64
    if mutation=='missing_expiry':row['data']='0x'
    with pytest.raises(ValueError):decode(row)

@pytest.mark.parametrize('mutation',['removed','wrong_wallet','outside_range','duplicate'])
def test_scan_rejects_invalid_rpc_logs(tmp_path,mutation):
    row=event()
    if mutation=='removed':row['removed']=True
    if mutation=='wrong_wallet':row['address']='0x'+'4'*40
    if mutation=='outside_range':row['blockNumber']='0xb'
    class Fake:
        def call(self,*args):return [row,row] if mutation=='duplicate' else [row]
    with pytest.raises(ValueError):scan(Fake(),10,10,tmp_path)
    assert not (tmp_path/'coverage_progress.json').exists()

def test_empty_ranges_contiguous_but_not_certification(tmp_path,monkeypatch):
    monkeypatch.setattr('analysis.scan_deposit_session_history.time.sleep',lambda _:None)
    class Fake:
        def call(self,method,params):return []
    manifest,rows=scan(Fake(),10,10010,tmp_path)
    assert [(r['from_block'],r['to_block']) for r in manifest]==[(10,5009),(5010,10009),(10010,10010)]
    assert rows==[]

def test_write_rpc_rejected_without_network():
    with pytest.raises(ValueError,match='READ_ONLY_METHOD'):
        RPC('https://polygon.drpc.org').call('eth_sendRawTransaction',[])
