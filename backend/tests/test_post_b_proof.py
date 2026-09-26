import copy
import pytest


def header(n,h):return {"number":hex(n),"hash":"0x"+h*64,"timestamp":"0x1"}


def test_finalized_qualification_pins_numeric_hash():
    from analysis.qualify_post_b_proofs import qualify_finalized
    calls=[]
    class RPC:
        def call(self,m,p):
            calls.append((m,p))
            return "0x89" if m=="eth_chainId" else header(23,"b") if p[0]=="latest" else header(22,"a")
    r=qualify_finalized(RPC())
    assert r["status"]=="PASS_PROVIDER_FINALIZED_READ"
    assert ("eth_getBlockByNumber",["0x16",False]) in calls
    assert calls.count(("eth_getBlockByNumber",["finalized",False]))==2


@pytest.mark.parametrize("mode",["unsupported","reorg","wrong_chain"])
def test_finalized_fail_closed(mode):
    from analysis.qualify_post_b_proofs import qualify_finalized
    class RPC:
        def call(self,m,p):
            if m=="eth_chainId":return "0x1" if mode=="wrong_chain" else "0x89"
            if p[0]=="finalized" and mode=="unsupported":raise ValueError("secret-endpoint")
            return header(23,"b") if p[0]=="latest" else header(22,"c" if p[0]=="0x16" and mode=="reorg" else "a")
    with pytest.raises(ValueError,match="^FINALIZED_UNPROVEN$"):qualify_finalized(RPC())


def proof():
    return dict(anchored_inventory_proven=True,anchor_number=22,anchor_hash="0x"+"a"*64,anchor_rechecked_hash="0x"+"a"*64,
        tail_end=24,tail_hash="0x"+"b"*64,ranges=[[23,23],[24,24]],tail_complete=True,
        witness_number=24,witness_hash="0x"+"b"*64,scan_observed_ms=100,
        witness_observed_ms=900,anchor_observed_ms=920,generation=1,
        account={k:dict(generation=1,complete=True,observed_ms=910) for k in ("balance","orders","trades","positions")})


def test_fresh_same_head_witness_preserves_old_scan_without_retiming():
    from analysis.qualify_post_b_proofs import evaluate_post_b
    e=proof();old=copy.deepcopy(e);r=evaluate_post_b(e,now=1000)
    assert not r["current_inventory_proven"] and e==old and r["scan_observed_ms"]==100
    assert r["reason"]=="NO_COMMON_POST_C_COMPLETENESS_WATERMARK"
    assert r["witness_observed_ms"]==900 and not r["ready_for_arm"] and not r["submit_allowed"]


@pytest.mark.parametrize("key,value,reason",[
 ("witness_number",25,"POST_B_TAIL_ADVANCED"),
 ("witness_hash","0x"+"c"*64,"TAIL_REORG"),
 ("anchor_rechecked_hash","0x"+"c"*64,"ANCHOR_REORG"),
 ("ranges",[[24,24]],"TAIL_GAP_OR_OVERLAP"),
 ("ranges",[[23,24],[24,24]],"TAIL_GAP_OR_OVERLAP"),
 ("witness_observed_ms",499,"GENERATION_STALE_500MS"),
 ("witness_observed_ms",1001,"GENERATION_STALE_500MS"),
 ("tail_complete",False,"TAIL_INCOMPLETE"),
 ("account",{},"ACCOUNT_GENERATION_PARTIAL")])
def test_post_b_blocks(key,value,reason):
    from analysis.qualify_post_b_proofs import evaluate_post_b
    e=proof();e[key]=value;r=evaluate_post_b(e,now=1000)
    assert not r["current_inventory_proven"] and r["reason"]==reason
    assert not r["ready_for_arm"] and not r["submit_allowed"]


def test_finalized_transport_is_explicit_opt_in(monkeypatch):
    from app.live.collateral_onchain import PublicRPC
    rpc=PublicRPC("0x"+"1"*40)
    with pytest.raises(ValueError,match="FORBIDDEN"):rpc.call("eth_getBlockByNumber",["finalized",False])
    class Opener:
        def open(self,request,timeout):raise TimeoutError()
    import urllib.request
    monkeypatch.setattr(urllib.request,"build_opener",lambda *a:Opener())
    rpc=PublicRPC("0x"+"1"*40,allow_finalized=True)
    with pytest.raises(RuntimeError,match="^PUBLIC_RPC_READ_FAILED$"):rpc.call("eth_getBlockByNumber",["finalized",False])
    assert rpc.calls[-1]["error_category"]=="TIMEOUT"


def test_anchor_precondition_and_partial_generation_rejected():
    from analysis.qualify_post_b_proofs import evaluate_post_b
    e=proof();e["anchored_inventory_proven"]=False
    assert evaluate_post_b(e,now=1000)["reason"]=="ANCHORED_INVENTORY_UNPROVEN"
    e=proof();e["account"]["orders"]["generation"]=2
    assert not evaluate_post_b(e,now=1000)["current_inventory_proven"]


def test_scan_is_exact_incremental_and_witness_does_not_retry(monkeypatch):
    import analysis.qualify_post_b_proofs as q
    calls=[];scans=[]
    class RPC:
        log_window=10
        def call(self,m,p):
            calls.append((m,p))
            if p[0]=="latest":return header(24 if len([x for x in calls if x[1][0]=="latest"])==1 else 25,"b")
            return header(int(p[0],16),"a")
    def scan(rpc,start,end,known,*,capture):
        scans.append((start,end));capture["balances"]={}
        return dict(status="PASS_SCOPED_READS",events_count=0,to_block=end,block_hash="0x"+("a" if end==22 else "b")*64)
    monkeypatch.setattr(q,"scan_ctf",scan)
    r=q.public_inventory(RPC(),{"snapshot":{"block_number":10,"block_hash":"0x"+"a"*64}},
        dict(to_block=20,block_hash="0x"+"a"*64,events_count=0,balances={},observed_ms=100),
        {"anchor":dict(number=22,hash="0x"+"a"*64)})
    assert scans==[(21,22),(23,24)]
    assert r["evaluation"]["reason"]=="POST_B_TAIL_ADVANCED" and r["attempts"]==1


def test_ws_capture_returns_exact_regression_and_always_cancels(monkeypatch):
    import asyncio
    import analysis.qualify_post_b_proofs as q
    from app.live.readonly_book_stream import StreamBook
    s=StreamBook("m","c",("one","two"),5000,clock=lambda:1071)
    cancelled=[]
    async def discovery(audit):return s
    async def fake_run():
        s.connected_generation()
        e=dict(event_type="book",market="c",asset_id="one",timestamp="1001",
            bids=[dict(price=".4",size="1")],asks=[dict(price=".6",size="1")])
        s.ingest(e);e["timestamp"]="1000"
        try:s.ingest(e)
        except ValueError:pass
        try:await asyncio.Future()
        finally:cancelled.append(True)
    monkeypatch.setattr(q,"discover_book",discovery);monkeypatch.setattr(s,"run",fake_run)
    r=asyncio.run(q.capture_ws([]))
    assert r["diagnostics"]["regression_event"]["delta_ms"]==-1
    assert cancelled and "books" not in r


def test_probe_without_target_never_reads_network_or_credentials(monkeypatch):
    import asyncio
    import analysis.qualify_post_b_proofs as q
    def forbidden(*a,**kw):raise AssertionError("NETWORK_OR_LEDGER_ACCESSED")
    monkeypatch.setattr(q,"PublicRPC",forbidden);monkeypatch.setattr(q,"read_genesis",forbidden)
    r=asyncio.run(q.run(False))
    assert not r["ready_for_arm"] and not r["submit_allowed"] and not r["credentials_loaded"]
