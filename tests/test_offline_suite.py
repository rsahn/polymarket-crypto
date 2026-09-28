import os,subprocess,sys,socket,json
from pathlib import Path
import pytest
import offline_suite as h

def test_guard_rejects_network_and_arbitrary_child_code():
    with pytest.raises(RuntimeError,match='NETWORK_FORBIDDEN'):socket.getaddrinfo('example.invalid',443)
    with pytest.raises(RuntimeError,match='SUBPROCESS'):subprocess.run([sys.executable,'-c','print(1)'])
    with pytest.raises(RuntimeError,match='SUBPROCESS'):subprocess.run('echo unsafe',shell=True)
    with pytest.raises(RuntimeError,match='SUBPROCESS'):subprocess.run(['git','rev-parse','HEAD'],cwd=h.ROOT,executable=sys.executable)
    with pytest.raises(RuntimeError,match='SUBPROCESS'):subprocess.run(['powershell','-Command','Get-Date'])
def test_real_secret_denied_synthetic_fixture_allowed(tmp_path):
    with pytest.raises(RuntimeError,match='REAL_SECRET_FILE_FORBIDDEN'):(h.ROOT/'.env').read_bytes()
    p=tmp_path/'.env';p.write_text('SYNTHETIC_ONLY=1');assert p.read_text()=='SYNTHETIC_ONLY=1'
    with pytest.raises(RuntimeError,match='ACL_NONFIXTURE_PATH'):subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',h.ACL_READER],input=json.dumps(str(h.ROOT)),text=True)
def test_scrubbed_child_environment_does_not_copy_secret_names(tmp_path,monkeypatch):
    monkeypatch.setenv('SIGNER_PRIVATE_KEY','synthetic-canary');monkeypatch.setenv('UNRELATED_API_TOKEN','synthetic-canary')
    env=h.clean_env(tmp_path)
    assert 'SIGNER_PRIVATE_KEY' not in env and 'UNRELATED_API_TOKEN' not in env and env['TEMP']==str(tmp_path)
def test_outside_and_linked_paths_are_not_fixture_roots(tmp_path,monkeypatch):
    assert not h.inside(h.ROOT,tmp_path)
    assert not h.inside(tmp_path/'..'/'outside',tmp_path)
    monkeypatch.setattr(Path,'is_symlink',lambda self:self==tmp_path)
    assert not h.inside(tmp_path/'x',tmp_path)
