import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pytest
from eth_utils import keccak
from eth_abi import encode
import close_session_history_gaps as gap
from verify_session_storage_paths import SOURCES,verify_writers,bind_runtime,walk,classify_events,verify_creation
from observe_legacy_settlements import statuses
from reconcile_legacy_chain import changes,TRANSFER,COLLATERAL,PAD,SINGLE,BATCH

@pytest.fixture(scope='module')
def compiler():return json.loads((SOURCES/'local_solc_output.json').read_text(encoding='utf-8'))

def test_reviewed_writer_inventory(compiler):
    writers,paths=verify_writers(compiler)
    assert len(writers)==13 and len(paths)==6

@pytest.mark.parametrize('function',['authorizeSessionSigner','revokeSessionSigner','revokeSessionSignerEmergency','authorizePasskeySessionSigner','revokePasskeySessionSigner','revokePasskeySessionSignerEmergency'])
def test_missing_mandatory_emit_rejected(compiler,function):
    altered=copy.deepcopy(compiler)
    target=next(n for n in walk(altered['sources']) if n.get('nodeType')=='FunctionDefinition' and n.get('name')==function)
    target['body']['statements'].pop()
    with pytest.raises(ValueError):verify_writers(altered)

def test_added_silent_setter_caller_rejected(compiler):
    altered=copy.deepcopy(compiler)
    nodes=altered['sources']['src/DepositWallet.sol']['ast']['nodes']
    contract=next(n for n in nodes if n.get('name')=='DepositWallet')
    duplicate=copy.deepcopy(next(n for n in contract['nodes'] if n.get('name')=='authorizeSessionSigner'))
    duplicate.update(id=999999,name='silentBackdoor');duplicate['body']['statements'].pop();contract['nodes'].append(duplicate)
    with pytest.raises(ValueError,match='CALLERS'):verify_writers(altered)

def test_bytecode_mutation_rejected(compiler):
    nodes={n['id']:n for n in walk(compiler['sources']) if 'id' in n and 'nodeType' in n}
    evm=compiler['contracts']['src/DepositWallet.sol']['DepositWallet']['evm']['deployedBytecode']
    record=next(r for r in json.loads((SOURCES.parent/'session_beacon_history_20261003/code_records.json').read_text()) if r['address']==gap.IMPL)
    bind_runtime(evm,nodes,gap.IMPL,record['code'])
    with pytest.raises(ValueError,match='MISMATCH'):bind_runtime(evm,nodes,gap.IMPL,'0xff'+record['code'][4:])

@pytest.mark.parametrize('event',['SessionSignerAuthorized(address,uint256)','SessionSignerRevoked(address)','SessionSignerRevokedEmergency(address)','PasskeySessionSignerAuthorized(bytes32,bytes32,bytes32,uint256)','PasskeySessionSignerRevoked(bytes32,bytes32,bytes32)','PasskeySessionSignerRevokedEmergency(bytes32,bytes32,bytes32)'])
def test_all_signer_events_prevent_zero_promotion(event):
    abi=json.loads((SOURCES/'sourcify_impl.txt').read_text(encoding='utf-8'))['abi']
    with pytest.raises(ValueError,match='HISTORICAL_SIGNER'):classify_events([dict(topics=['0x'+keccak(text=event).hex()])],abi)

def test_unknown_event_fail_closed():
    with pytest.raises(ValueError):classify_events([dict(topics=['0x'+'00'*32])],[])

def test_actual_creation_initcode():
    trace=json.loads((SOURCES/'genesis_call_trace.json').read_text())
    runtime=next(r['code'] for r in json.loads((SOURCES.parent/'session_beacon_history_20261003/code_records.json').read_text()) if r['address']==gap.WALLET)
    assert verify_creation(trace,runtime)['type']=='CREATE2'
    create=next(n for n in walk(trace) if n.get('type')=='CREATE2' and n.get('to','').lower()==gap.WALLET)
    create['input']='0xff'+create['input'][4:]
    with pytest.raises(ValueError,match='INITCODE'):verify_creation(trace,runtime)

def test_checkpoint_skips_network(tmp_path,monkeypatch):
    item=dict(from_block=1,to_block=2,logs=[],sha256=gap.digest([]))
    (tmp_path/'range_1_2.json').write_text(json.dumps(item))
    monkeypatch.setattr(gap,'RPC',lambda *a:pytest.fail('validated checkpoint must not be refetched'))
    assert gap.resume_range(tmp_path,gap.SECONDARY,gap.WALLET,1,2)==item

def test_corrupt_checkpoint_rejected(tmp_path):
    (tmp_path/'range_1_2.json').write_text(json.dumps(dict(from_block=1,to_block=2,logs=[],sha256='bad')))
    with pytest.raises(ValueError):gap.resume_range(tmp_path,gap.SECONDARY,gap.WALLET,1,2)

@pytest.mark.parametrize('state',['MATCHED','MINED','RETRYING'])
def test_pending_trade_never_terminal(state):
    result=statuses([dict(id='a',status=state)])
    assert result[state]==1 and result['CONFIRMED']==0 and result['FAILED']==0

def test_unknown_trade_status_rejected():
    with pytest.raises(ValueError):statuses([dict(id='a',status='SETTLED')])

@pytest.mark.parametrize('state',['MATCHED','MINED','RETRYING','CONFIRMED','FAILED'])
def test_documented_wire_prefix_has_same_semantics(state):
    assert statuses([dict(id='a',status='TRADE_STATUS_'+state)])==statuses([dict(id='a',status=state)])

def test_duplicate_trade_rejected():
    with pytest.raises(ValueError):statuses([dict(id='a',status='CONFIRMED')]*2)

def test_cash_in_out_and_self_transfer():
    other='0x'+'00'*32
    def row(a,b,n):return dict(address=COLLATERAL,topics=[TRANSFER,a,b],data='0x'+n.to_bytes(32,'big').hex())
    cash,pos=changes([row(other,PAD,100),row(PAD,other,20),row(PAD,PAD,50)])
    assert cash==80 and pos=={}

@pytest.mark.parametrize('topic,types,values',[(SINGLE,['uint256','uint256'],[17,4]),(BATCH,['uint256[]','uint256[]'],[[17],[4]])])
def test_positions_single_and_batch(topic,types,values):
    cash,pos=changes([dict(address=COLLATERAL,topics=[topic,'0x'+'00'*32,'0x'+'00'*32,PAD],data='0x'+encode(types,values).hex())])
    assert cash==0 and pos[(COLLATERAL,'17')]==4
