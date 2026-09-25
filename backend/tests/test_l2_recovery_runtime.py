import json
import os
import time
import traceback
from pathlib import Path
import pytest

from app.live.l2_recovery_runtime import Recovery, FixedGetTransport, ProtectedStore, EXPECTED, validate_triplet

CREDS={"apiKey":"fixture-api-key", "secret":"fixture-secret-canary", "passphrase":"fixture-passphrase-canary"}
CANARIES=list(CREDS.values())+["fixture-signature-canary", "fixture-private-key-canary"]

class Platform:
    def create_private_directory(self,p):p.mkdir()
    def protect(self,data):return b"FAKE_ENCRYPTED" # real DPAPI tested separately
    def publish(self,src,dst):
        if dst.exists():raise FileExistsError()
        os.rename(src,dst)

class Transport:
    def __init__(self,payload=None,error=False):self.calls=[];self.payload=CREDS if payload is None else payload;self.error=error
    def get(self,path,headers=None):
        self.calls.append(path)
        if path=="/time":return int(time.time())
        if self.error:raise TimeoutError(CANARIES[1])
        return self.payload

class Signer:
    def __init__(self):self.calls=0
    def headers(self,stamp):
        self.calls+=1
        return {"POLY_ADDRESS":EXPECTED,"POLY_NONCE":"0","POLY_TIMESTAMP":str(stamp),"POLY_SIGNATURE":CANARIES[-2]}

def setup(tmp_path,payload=None,error=False,platform=None):
    store=ProtectedStore(tmp_path/'vault',platform=platform or Platform())
    t=Transport(payload,error);s=Signer();r=Recovery(t,s,store)
    return r,t,s,store

def test_success_simulated(tmp_path,capsys):
    r,t,s,store=setup(tmp_path)
    result=r.run(confirmed=True)
    assert result['success'] and result['stored']
    assert t.calls==['/time','/auth/derive-api-key'] and s.calls==1
    assert store.destination.read_bytes()==b'FAKE_ENCRYPTED'
    assert list(store.directory.iterdir())==[store.destination]
    assert not capsys.readouterr().out

@pytest.mark.parametrize('payload',[{}, {'apiKey':'x','secret':'x'}, [], 'invalid', {**CREDS,'secret':''}, {**CREDS,'secret':1}, {**CREDS,'secret':' x'}, {**CREDS,'extra':'x'}, {**CREDS,'passphrase':'x\ny'}])
def test_invalid_triplet_never_written(tmp_path,payload):
    r,t,s,store=setup(tmp_path,payload)
    assert not r.run(confirmed=True)['success']
    assert not store.destination.exists()
    assert not list(store.directory.glob('*.tmp'))

def test_timeout_and_second_run_no_retry(tmp_path):
    r,t,s,store=setup(tmp_path,error=True)
    assert not r.run(confirmed=True)['success']
    assert not r.run(confirmed=True)['success']
    assert t.calls.count('/auth/derive-api-key')==1
    assert not store.destination.exists()

def test_confirmation_required_before_io(tmp_path):
    r,t,s,store=setup(tmp_path)
    assert not r.run(confirmed=False)['success']
    assert t.calls==[] and s.calls==0 and not store.directory.exists()

@pytest.mark.parametrize('kwargs',[{'signer':'0x'+'1'*40},{'nonce':1},{'nonce':True},{'chain_id':1},{'environment':'test'}])
def test_fixed_identity_rejects(kwargs,tmp_path):
    with pytest.raises(ValueError):Recovery(Transport(),Signer(),ProtectedStore(tmp_path/'x',platform=Platform()),**kwargs)

def test_existing_file_preserved_before_io(tmp_path):
    r,t,s,store=setup(tmp_path)
    store.directory.mkdir();store.destination.write_bytes(b'existing')
    assert not r.run(confirmed=True)['success'] and t.calls==[]
    assert store.destination.read_bytes()==b'existing'

def test_interrupted_write_cleanup(tmp_path,monkeypatch):
    r,t,s,store=setup(tmp_path)
    def broken(data):
        store.temporary.write_bytes(b'partial-encrypted')
        raise OSError(CANARIES[0])
    monkeypatch.setattr(store,'_write_ciphertext',broken)
    assert not r.run(confirmed=True)['success']
    assert not store.destination.exists() and not store.temporary.exists()

def test_no_secret_in_outputs_or_report(tmp_path,capsys,caplog):
    class BrokenSigner:
        def headers(self,stamp):raise RuntimeError(' '.join(CANARIES))
    r,t,s,store=setup(tmp_path);r.signer=BrokenSigner()
    result=r.run(confirmed=True)
    outputs=capsys.readouterr();text=outputs.out+outputs.err+caplog.text+json.dumps(result)+repr(r)
    assert all(c not in text for c in CANARIES)
    assert not result['success']

class Response:
    status=200
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.data

class Opener:
    def __init__(self):self.requests=[]
    def open(self,request,timeout):
        self.requests.append(request)
        return Response(str(int(time.time())).encode() if request.full_url.endswith('/time') else json.dumps(CREDS).encode())

def test_get_only_transport_second_derive_and_no_post():
    o=Opener();t=FixedGetTransport(opener=o)
    assert not hasattr(t,'post') and not hasattr(t,'create_api_key') and not hasattr(t,'create_or_derive_api_key')
    t.get('/time');t.get('/auth/derive-api-key',Signer().headers(int(time.time())))
    with pytest.raises(ValueError):t.get('/auth/derive-api-key',{})
    assert len(o.requests)==2 and all(r.get_method()=='GET' for r in o.requests)

@pytest.mark.parametrize('route',['/auth/api-key','/time?nonce=1','https://evil.test/time','POST','/balance-allowance'])
def test_transport_wrong_route(route):
    o=Opener();t=FixedGetTransport(opener=o)
    with pytest.raises(ValueError):t.get(route)
    assert not o.requests

def test_redirect_rejected():
    class Redirect(Opener):
        def open(self,*a,**kw):
            r=Response(b'ignored');r.status=302;return r
    with pytest.raises(ValueError):FixedGetTransport(opener=Redirect()).get('/time')

def test_duplicate_json_field_rejected():
    class Duplicate(Opener):
        def open(self,*a,**kw):return Response(b'{"secret":"a","secret":"b"}')
    with pytest.raises(ValueError):FixedGetTransport(opener=Duplicate()).get('/time')

def test_windows_dpapi_acl_and_atomic_publication(tmp_path):
    import ctypes
    import subprocess
    from app.live.l2_windows_storage import WindowsProtection, Blob
    platform=WindowsProtection()
    store=ProtectedStore(tmp_path/'protected-fixture',platform=platform)
    try:
        store.prepare();store.commit(CREDS)
        ciphertext=store.destination.read_bytes()
        assert all(x.encode() not in ciphertext for x in CANARIES)
        buffer=(ctypes.c_ubyte*len(ciphertext)).from_buffer_copy(ciphertext)
        incoming=Blob(len(ciphertext),buffer);outgoing=Blob()
        platform.crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
        try:
            assert platform.crypt.CryptUnprotectData(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing))
            assert json.loads(ctypes.string_at(outgoing.data,outgoing.size))['credentials']==CREDS
        finally:
            if outgoing.data:platform.kernel.LocalFree(outgoing.data)
        # Public ACL metadata only; never pass credential content to another process.
        command="$a=[System.IO.Directory]::GetAccessControl($args[0]); @{protected=$a.AreAccessRulesProtected; rules=@($a.Access | ForEach-Object { @{sid=$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value; type=$_.AccessControlType.ToString()} })} | ConvertTo-Json -Depth 4"
        # Pass path via stdin JSON instead of shell interpolation.
        command="$p=([Console]::In.ReadToEnd() | ConvertFrom-Json); "+command.replace('$args[0]','$p')
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],input=json.dumps(str(store.directory)),text=True,capture_output=True,check=True)
        acl=json.loads(result.stdout)
        assert acl['protected'] is True, result.stderr
        assert len(acl['rules'])==1 and acl['rules'][0]=={'sid':platform.sid,'type':'Allow'}
        other=store.directory/'other.tmp';other.write_bytes(b'other')
        with pytest.raises(ValueError):platform.publish(other,store.destination)
        assert store.destination.read_bytes()==ciphertext
        other.unlink()
    finally:
        if store.destination.exists():store.destination.unlink()
        store.cleanup()
        if store.directory.exists():store.directory.rmdir()



def test_local_signer_uses_only_validated_identity_and_clobauth(tmp_path,monkeypatch):
    from app.live.l2_recovery_runtime import ExistingLocalSigner
    from eth_account import Account
    from types import SimpleNamespace
    p=tmp_path/'fixture.env';p.write_text('SIGNER_PRIVATE_KEY=fixture-private-key-canary\nREAL_ORDERS_ENABLED=false\nLIVE_EXECUTION_ARMED=false\n')
    seen=[]
    class FakeAccount:
        address=EXPECTED
        def sign_typed_data(self,*,full_message):
            seen.append(full_message)
            return SimpleNamespace(signature=bytes([1])*65)
    monkeypatch.setattr(Account,'from_key',lambda key:FakeAccount())
    headers=ExistingLocalSigner(p).headers(123)
    assert headers['POLY_ADDRESS']==EXPECTED and headers['POLY_NONCE']=='0'
    assert seen[0]['primaryType']=='ClobAuth' and seen[0]['domain']['chainId']==137
    assert seen[0]['message']['nonce']==0
    FakeAccount.address='0x'+'2'*40
    with pytest.raises(ValueError,match='LOCAL_SIGNER_REJECTED'):ExistingLocalSigner(p).headers(123)
    assert len(seen)==1

def test_dpapi_failure_leaves_no_plaintext(tmp_path):
    class Broken(Platform):
        def protect(self,data):raise RuntimeError(CANARIES[1])
    r,t,s,store=setup(tmp_path,platform=Broken())
    assert not r.run(confirmed=True)['success'] and not store.directory.exists()

def test_cli_preview_does_not_touch_private_key_or_network(tmp_path,monkeypatch,capsys):
    import importlib.util
    source=Path(__file__).resolve().parents[2]/'analysis/recover_existing_l2_local.py'
    spec=importlib.util.spec_from_file_location('isolated_l2',source)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    def forbidden(*a,**kw):raise AssertionError('PRIVATE_OR_NETWORK_ACCESS')
    monkeypatch.setattr(m.ExistingLocalSigner,'headers',forbidden)
    monkeypatch.setattr(m.FixedGetTransport,'get',forbidden)
    monkeypatch.setattr(Path,'read_text',forbidden)
    assert m.main(['--preview','--output',str(tmp_path/'preview.json')])==0
    text=capsys.readouterr().out
    assert '0x9348...203a' in text and all(c not in text for c in CANARIES)

def test_cli_rejects_secret_bearing_arguments(capsys):
    import importlib.util
    source=Path(__file__).resolve().parents[2]/'analysis/recover_existing_l2_local.py'
    spec=importlib.util.spec_from_file_location('isolated_l2',source)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    with pytest.raises(SystemExit):m.main(['--private-key',CANARIES[-1]])
    output=capsys.readouterr()
    assert CANARIES[-1] not in output.out+output.err

def load_cli():
    import importlib.util
    source=Path(__file__).resolve().parents[2]/'analysis/recover_existing_l2_local.py'
    spec=importlib.util.spec_from_file_location('isolated_l2',source)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.mark.parametrize('confirmation',['wrong',''])
def test_cli_refuses_confirmation_before_network(tmp_path,monkeypatch,confirmation):
    from types import SimpleNamespace
    m=load_cli();called=[]
    monkeypatch.setattr(m.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr('builtins.input',lambda:confirmation)
    monkeypatch.setattr(m,'FixedGetTransport',lambda:called.append('forbidden'))
    assert m.main(['--recover-existing','--output',str(tmp_path/'report.json')])==2
    assert called==[]


def test_cli_success_is_fake_only_and_report_scrubbed(tmp_path,monkeypatch,capsys):
    from types import SimpleNamespace
    m=load_cli()
    monkeypatch.setattr(m.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr('builtins.input',lambda:m.CONFIRMATION)
    monkeypatch.setattr(m,'storage_directory',lambda root:tmp_path/'fake-vault')
    monkeypatch.setattr(m,'WindowsProtection',Platform)
    monkeypatch.setattr(m,'FixedGetTransport',Transport)
    monkeypatch.setattr(m,'ExistingLocalSigner',lambda path:Signer())
    p=tmp_path/'report.json'
    assert m.main(['--recover-existing','--output',str(p)])==0
    report=json.loads(p.read_text());assert report['success'] and report['stored']
    outputs=capsys.readouterr()
    assert all(c not in outputs.out+outputs.err+p.read_text() for c in CANARIES)


def test_cli_preexisting_report_blocks_every_sensitive_operation(tmp_path,monkeypatch):
    m=load_cli();p=tmp_path/'report.json';p.write_text('existing')
    def forbidden(*a,**kw):raise AssertionError('NETWORK_OR_KEY')
    monkeypatch.setattr(m,'FixedGetTransport',forbidden)
    monkeypatch.setattr(m,'ExistingLocalSigner',forbidden)
    assert m.main(['--recover-existing','--output',str(p)])==2
    assert p.read_text()=='existing'


def test_failed_atomic_publish_removes_encrypted_stage(tmp_path):
    class Broken(Platform):
        def publish(self,src,dst):raise OSError(' '.join(CANARIES))
    r,t,s,store=setup(tmp_path,platform=Broken())
    result=r.run(confirmed=True)
    assert not result['stored'] and not store.destination.exists() and not store.temporary.exists()
    assert all(c not in json.dumps(result) for c in CANARIES)


def test_network_failure_outputs_and_storage_do_not_leak(tmp_path,capsys,caplog):
    r,t,s,store=setup(tmp_path,error=True)
    report=r.run(confirmed=True)
    out=capsys.readouterr()
    assert all(c not in json.dumps(report)+out.out+out.err+caplog.text for c in CANARIES)
    assert not store.directory.exists()

@pytest.mark.parametrize('stamp',[None,'123',True,0])
def test_invalid_server_time_prevents_key_loading(tmp_path,stamp):
    r,t,s,store=setup(tmp_path)
    t.get=lambda *a,**kw:stamp
    assert not r.run(confirmed=True)['success'] and s.calls==0


def test_storage_refuses_repository_path(tmp_path,monkeypatch):
    from app.live.l2_windows_storage import storage_directory
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    with pytest.raises(ValueError):storage_directory(tmp_path)


def test_windows_interruption_cleans_ciphertext_and_permissions(tmp_path,monkeypatch):
    from app.live.l2_windows_storage import WindowsProtection
    r,t,s,store=setup(tmp_path,platform=WindowsProtection())
    def broken(data):
        store.temporary.write_bytes(data[:8]);raise OSError('simulated-interruption')
    monkeypatch.setattr(store,'_write_ciphertext',broken)
    assert not r.run(confirmed=True)['success']
    assert not store.directory.exists()

def test_offline_storage_validation_uses_only_fixture(tmp_path,monkeypatch,capsys):
    m=load_cli()
    monkeypatch.setattr(m,'storage_directory',lambda root:tmp_path/'unused-vault')
    def forbidden(*a,**kw):raise AssertionError('NETWORK_OR_KEY')
    monkeypatch.setattr(m.FixedGetTransport,'get',forbidden)
    monkeypatch.setattr(m.ExistingLocalSigner,'headers',forbidden)
    path=tmp_path/'report.json'
    assert m.main(['--preview','--validate-storage','--output',str(path)])==0
    report=json.loads(path.read_text())
    assert report['storage_validated'] and not report['derive_attempted'] and not report['signature_produced']
    assert not list(tmp_path.glob('PolymarketD6L2-validation-*'))


def test_real_redirect_handler_never_follows():
    from app.live.l2_recovery_runtime import NoRedirect
    with pytest.raises(ValueError,match='REDIRECT_FORBIDDEN'):
        NoRedirect().redirect_request(None,None,302,'redirect',{},'https://evil.test')


def test_transport_timeout_spends_budget():
    class Timeout(Opener):
        def open(self,*a,**kw):raise TimeoutError(' '.join(CANARIES))
    t=FixedGetTransport(opener=Timeout())
    for route in ('/time','/auth/derive-api-key'):
        with pytest.raises(ValueError) as error:t.get(route)
        assert all(c not in str(error.value) for c in CANARIES)
