import json
from app.live.l2_existing_reader import validate_envelope, unique, EXPECTED
import pytest


def envelope():
    return dict(version=1,environment='production',chain_id=137,nonce=0,signer=EXPECTED,credentials=dict(apiKey='fakekey',secret='fakesecret',passphrase='fakepass'))

@pytest.mark.parametrize('change',[{'nonce':1},{'nonce':False},{'chain_id':1},{'signer':'wrong'},{'environment':'test'},{'credentials':{}},{'extra':True}])
def test_bad_binding(change):
    with pytest.raises(ValueError):validate_envelope({**envelope(),**change})

def test_valid():assert set(validate_envelope(envelope()))=={'apiKey','secret','passphrase'}

def test_duplicate():
    with pytest.raises(ValueError):json.loads('{"nonce":0,"nonce":1}',object_pairs_hook=unique)


def test_real_fixture_reader(tmp_path,monkeypatch,capsys):
    from app.live.l2_windows_storage import WindowsProtection
    from app.live.l2_recovery_runtime import ProtectedStore
    import app.live.l2_existing_reader as m
    store=ProtectedStore(tmp_path/'fixture',platform=WindowsProtection())
    try:
        store.prepare();store.commit(envelope()['credentials'])
        monkeypatch.setattr(m,'storage_directory',lambda root:store.directory)
        creds,report=m.load_existing(tmp_path)
        assert creds==envelope()['credentials'] and report['storage_validated']
        out=capsys.readouterr()
        assert not out.out and not out.err
        assert all(v not in json.dumps(report) for v in creds.values())
    finally:
        if store.destination.exists():store.destination.unlink()
        if store.directory.exists():store.directory.rmdir()

def test_qualification_wrapper_uses_existing_only(tmp_path,monkeypatch,capsys):
    import importlib.util,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root/'analysis'))
    spec=importlib.util.spec_from_file_location('stored_probe',root/'analysis/qualify_stored_l2.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'load_existing',lambda root:(envelope()['credentials'],{'storage_validated':True}))
    monkeypatch.setattr(m,'leak_check',lambda creds:{'detected':False})
    async def fake(config):
        assert config['READONLY_CLOB_API_SECRET']=='fakesecret'
        assert 'SIGNER_PRIVATE_KEY' not in config
        return {'qualification':{'time':{'status':'PASS'}},'provenance':{'live_flags_disabled':{}},'complete':False}
    monkeypatch.setattr(m,'qualify',fake)
    monkeypatch.setattr(sys,'argv',['probe','--network'])
    m.main()
    text=capsys.readouterr().out
    assert all(v not in text for v in envelope()['credentials'].values())
    assert json.loads(text)['derive_attempted'] is False
    assert json.loads(text)['status']=='AUTHENTICATED_READ_ONLY_NOT_READY'

