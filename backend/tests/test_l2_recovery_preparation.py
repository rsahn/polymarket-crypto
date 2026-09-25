import importlib.util
from pathlib import Path
import pytest

SIGNER="0x"+"1"*40
ROOT=Path(__file__).resolve().parents[2]

def policy():
    from app.live.l2_recovery_preparation import RecoveryPolicy
    p=RecoveryPolicy(SIGNER);p.preview();p.confirm(SIGNER,nonce=0)
    return p

@pytest.mark.parametrize("method",["POST","DELETE","PUT","PATCH"])
def test_mutating_method_aborts(method):
    p=policy()
    with pytest.raises(ValueError):p.permit(method,"https://clob.polymarket.com/time")
    with pytest.raises(ValueError):p.permit("GET","https://clob.polymarket.com/time")

@pytest.mark.parametrize("nonce",[1,-1,True,"0"])
def test_nonzero_or_untyped_nonce_rejected(nonce):
    from app.live.l2_recovery_preparation import RecoveryPolicy
    with pytest.raises(ValueError):RecoveryPolicy(SIGNER,nonce=nonce)

@pytest.mark.parametrize("url",["https://clob.polymarket.com/auth/api-key","https://evil.test/time","https://clob.polymarket.com/time?nonce=1","http://clob.polymarket.com/time","https://clob.polymarket.com/balance-allowance"])
def test_wrong_route_aborts(url):
    with pytest.raises(ValueError):policy().permit("GET",url)


def test_preview_and_separate_confirmation_required():
    from app.live.l2_recovery_preparation import RecoveryPolicy
    p=RecoveryPolicy(SIGNER)
    with pytest.raises(ValueError):p.confirm(SIGNER,nonce=0)
    p=RecoveryPolicy(SIGNER);p.preview()
    with pytest.raises(ValueError):p.permit("GET","https://clob.polymarket.com/time")


def test_second_derivation_rejected_even_after_failure():
    p=policy();p.permit("GET","https://clob.polymarket.com/time");p.time_result(200,1000,1000)
    p.permit("GET","https://clob.polymarket.com/auth/derive-api-key")
    with pytest.raises(ValueError):p.permit("GET","https://clob.polymarket.com/auth/derive-api-key")


def test_redirect_aborts_without_following():
    p=policy();p.permit("GET","https://clob.polymarket.com/time")
    with pytest.raises(ValueError):p.time_result(302,1000,1000)
    with pytest.raises(ValueError):p.permit("GET","https://clob.polymarket.com/auth/derive-api-key")

@pytest.mark.parametrize("operation",["create_api_key","create_or_derive","AsyncSecureClient.create","AsyncSecureClient._create","_ensure_wallet_ready","relayer","rpc","cancel_order","allowance_update","deploy"])
def test_creation_or_side_effect_operation_rejected(operation):
    with pytest.raises(ValueError):policy().permit(operation,"https://clob.polymarket.com/auth/derive-api-key")


def test_other_signer_confirmation_rejected():
    from app.live.l2_recovery_preparation import RecoveryPolicy
    p=RecoveryPolicy(SIGNER);p.preview()
    with pytest.raises(ValueError):p.confirm("0x"+"2"*40,nonce=0)


def test_preview_does_not_load_private_key_or_config(monkeypatch,capsys,tmp_path):
    spec=importlib.util.spec_from_file_location("recovery_preview",ROOT/"analysis/l2_existing_credential_recovery.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m,"ROOT",tmp_path,raising=False)
    monkeypatch.setenv("L2_RECOVERY_EXPECTED_SIGNER",SIGNER)
    monkeypatch.setenv("SIGNER_PRIVATE_KEY","DO_NOT_READ_PRIVATE_KEY")
    def forbidden(*a,**k):raise AssertionError("NO_FILE_READS")
    monkeypatch.setattr(Path,"read_text",forbidden)
    assert m.main(["--preview"])==0
    text=capsys.readouterr().out
    assert "DO_NOT_READ_PRIVATE_KEY" not in text and "ClobAuthDomain" in text


def test_execution_mode_unavailable():
    spec=importlib.util.spec_from_file_location("recovery_preview",ROOT/"analysis/l2_existing_credential_recovery.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    with pytest.raises(SystemExit):m.main(["--execute"])


def test_derivation_redirect_consumes_and_aborts():
    p=policy();p.permit("GET","https://clob.polymarket.com/time");p.time_result(200,1000,1000)
    p.permit("GET","https://clob.polymarket.com/auth/derive-api-key")
    with pytest.raises(ValueError):p.derive_result(307)
    with pytest.raises(ValueError):p.permit("GET","https://clob.polymarket.com/auth/derive-api-key")

@pytest.mark.parametrize("kw",[{"chain_id":1},{"environment":"test"}])
def test_other_environment_rejected(kw):
    from app.live.l2_recovery_preparation import RecoveryPolicy
    with pytest.raises(ValueError):RecoveryPolicy(SIGNER,**kw)


def load_preview_module():
    spec=importlib.util.spec_from_file_location("recovery_preview",ROOT/"analysis/l2_existing_credential_recovery.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_preview_writes_only_whitelisted_public_fields(monkeypatch,tmp_path,capsys):
    import json
    m=load_preview_module();monkeypatch.setattr(m,"ROOT",tmp_path,raising=False)
    allowed={"L2_RECOVERY_EXPECTED_SIGNER":SIGNER,"REAL_ORDERS_ENABLED":"false","LIVE_EXECUTION_ARMED":"false"}
    class PublicEnvironment:
        def get(self,key,default=None):
            assert key in allowed,"SECRET_ENV_READ"
            return allowed.get(key,default)
    from types import SimpleNamespace
    monkeypatch.setattr(m,"os",SimpleNamespace(environ=PublicEnvironment()))
    assert m.main(["--preview"])==0
    data=json.loads((tmp_path/"L2_RECOVERY_PREVIEW.json").read_text())
    assert set(data)=={"chain_id","environment","expected_signer","nonce","eip712_domain","eip712_type","endpoint","method"}
    assert SIGNER not in json.dumps(data)
    assert json.loads(capsys.readouterr().out)==data


def test_preview_never_overwrites_report(monkeypatch,tmp_path):
    m=load_preview_module();monkeypatch.setattr(m,"ROOT",tmp_path,raising=False)
    p=tmp_path/"L2_RECOVERY_PREVIEW.json";p.write_text("existing")
    monkeypatch.setenv("L2_RECOVERY_EXPECTED_SIGNER",SIGNER)
    assert m.main(["--preview"])==4
    assert p.read_text()=="existing"


def test_missing_signer_emits_blocked_preview_without_fallback(monkeypatch,tmp_path):
    import json
    m=load_preview_module();monkeypatch.setattr(m,"ROOT",tmp_path,raising=False)
    monkeypatch.delenv("L2_RECOVERY_EXPECTED_SIGNER",raising=False)
    monkeypatch.setenv("POLYMARKET_WALLET_ADDRESS",SIGNER)
    assert m.main(["--preview"])==2
    assert json.loads((tmp_path/"L2_RECOVERY_PREVIEW.json").read_text())["expected_signer"]=="NOT_CONFIGURED"


def test_unknown_cli_argument_does_not_echo_secret(capsys):
    m=load_preview_module()
    with pytest.raises(SystemExit):m.main(["--preview","--private-key","NEVER_ECHO_THIS"])
    out=capsys.readouterr()
    assert "NEVER_ECHO_THIS" not in out.out+out.err


@pytest.mark.parametrize("signer", ["", "0x1234", "0x"+"g"*40, "0x"+"1"*64, " "+SIGNER])
def test_invalid_expected_signer_blocks_preview_and_policy(monkeypatch,tmp_path,capsys,signer):
    import json
    from app.live.l2_recovery_preparation import RecoveryPolicy
    m=load_preview_module();monkeypatch.setattr(m,"ROOT",tmp_path)
    monkeypatch.setenv("L2_RECOVERY_EXPECTED_SIGNER",signer)
    assert m.main(["--preview"])==2
    assert json.loads(capsys.readouterr().out)["expected_signer"]=="NOT_CONFIGURED"
    with pytest.raises(ValueError):RecoveryPolicy(signer)
