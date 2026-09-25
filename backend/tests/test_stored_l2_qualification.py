import asyncio,json,time,sqlite3
from types import SimpleNamespace
import pytest
from app.live.stored_l2_qualification import qualify, local_snapshot

WALLET='0x'+'1'*40
SECRET='fixture-order-id-or-secret'

def config():return {'READONLY_SIGNER_ADDRESS':WALLET,'POLYMARKET_WALLET_ADDRESS':WALLET,'READONLY_SIGNATURE_TYPE':'0','READONLY_CLOB_API_KEY':'fake-key','READONLY_CLOB_API_SECRET':'ZmFrZQ==','READONLY_CLOB_API_PASSPHRASE':'fake-pass'}

class Pages:
    def __init__(self,rows,calls,name,cursor=None):self.rows,self.calls,self.name,self.cursor=rows,calls,name,cursor
    async def first_page(self):
        self.calls.append(self.name+('2' if self.cursor else '1'))
        return SimpleNamespace(items=self.rows if self.cursor else [],has_more=not bool(self.cursor),next_cursor=None if self.cursor else 'next')
    def from_cursor(self,c):return Pages(self.rows,self.calls,self.name,c)


def run(balance_fail=False,orders_fail=False,time_fail=False,local=None):
    calls=[]
    class Http:
        def __init__(self,base,routes,**kw):pass
        async def get_json(self,path):
            calls.append('time')
            if time_fail:raise ValueError(SECRET)
            return int(time.time())
    class Client:
        def __init__(self,**kw):pass
        async def get_balance_allowance(self,**kw):
            calls.append('balance')
            if balance_fail:raise ValueError(SECRET)
            from polymarket._internal.environment import PRODUCTION_CONFIG as env
            return {'balance':'1000000','allowances':{env.standard_exchange:'25000000'}}
        def list_open_orders(self):
            if orders_fail:
                calls.append('orders-failed');raise ValueError(SECRET)
            return Pages([{'id':SECRET,'maker_address':WALLET}],calls,'orders')
        def list_account_trades(self):return Pages([{'id':SECRET}],calls,'trades')
        def list_positions(self,**kw):return Pages([{'wallet':WALLET,'asset_id':'12','current_size':'3'}],calls,'positions')
    cfg=config();cfg['READONLY_EXECUTION_STATE_DB']=local
    result=asyncio.run(qualify(cfg,transport=Http,client_factory=Client))
    return result,calls


def test_order_and_pagination_and_redaction():
    r,c=run()
    assert c==['time','balance','orders1','orders2','trades1','trades2','positions1','positions2']
    assert r['qualification']['balance_allowance']['balance_raw']=='1000000'
    assert r['qualification']['orders']['count']==1
    text=json.dumps(r)
    assert SECRET not in text and WALLET not in text and 'fake-pass' not in text
    assert r['complete'] is False and r['submit_allowed'] is False

@pytest.mark.parametrize('kwargs',[{'balance_fail':True},{'orders_fail':True}])
def test_independent_stages_after_failure_no_retry(kwargs):
    r,c=run(**kwargs)
    assert r['qualification']['trades']['status']=='PASS_READ_ONLY'
    assert r['qualification']['positions']['status']=='PASS_INDEX_ONLY'
    assert c.count('balance')==1 and c.count('orders-failed')<=1
    assert SECRET not in json.dumps(r)


def test_time_failure_prevents_all_auth_reads():
    r,c=run(time_fail=True)
    assert c==['time','positions1','positions2']
    assert r['qualification']['orders']['reason']=='PUBLIC_TIME_PREFLIGHT_FAILED'


def test_local_closed_is_not_remote_proof(tmp_path):
    p=tmp_path/'state.db'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE execution_state (id INTEGER PRIMARY KEY,value TEXT)')
        db.execute('INSERT INTO execution_state VALUES(1,?)',(json.dumps({'phase':'CLOSED','open_shares':0}),))
    before=p.read_bytes()
    r,c=run(local=str(p))
    stage=r['qualification']['reconciliation']
    assert stage['local_closed'] and stage['status']=='BLOCKED' and stage['complete'] is False
    assert p.read_bytes()==before


def test_missing_local_not_inferred_flat():
    r,c=run()
    assert r['qualification']['reconciliation']['reason']=='LOCAL_STATE_NOT_CONFIGURED'
