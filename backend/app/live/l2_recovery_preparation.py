"""Offline preparation only. No transport, signer, private-key reader or secret sink.
Execution must remain disabled until a separately authorized implementation supplies
an interactive confirmation, late protected-key access, and exclusive protected storage.
"""
import re
from dataclasses import dataclass

TIME="https://clob.polymarket.com/time"
DERIVE="https://clob.polymarket.com/auth/derive-api-key"


def preview(expected_signer):
    valid=isinstance(expected_signer,str) and bool(re.fullmatch(r"0x[0-9a-fA-F]{40}",expected_signer))
    return {"chain_id":137,"environment":"production Polygon",
        "expected_signer":expected_signer[:6]+"..."+expected_signer[-4:] if valid else "NOT_CONFIGURED",
        "nonce":0,"eip712_domain":{"name":"ClobAuthDomain","version":"1","chainId":137},
        "eip712_type":"ClobAuth","endpoint":DERIVE,"method":"GET"}


@dataclass(frozen=True)
class Plan:
    signer: str
    nonce: int=0
    chain_id: int=137
    environment: str="production"
    def __post_init__(self):
        if not isinstance(self.signer,str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}",self.signer):raise ValueError("EXPECTED_SIGNER_REQUIRED")
        if type(self.nonce) is not int or self.nonce!=0:raise ValueError("NONCE_MUST_BE_ZERO")
        if type(self.chain_id) is not int or self.chain_id!=137 or self.environment!="production":raise ValueError("PRODUCTION_POLYGON_ONLY")


class RecoveryPolicy:
    """Single-use state machine, tested with synthetic HTTP results, never sends I/O.
    A refused transition permanently aborts this instance. A permit consumes its
    budget BEFORE a future I/O attempt, so timeouts must not trigger retries.
    """
    def __init__(self,signer,*,nonce=0,chain_id=137,environment="production"):
        self.plan=Plan(signer,nonce,chain_id,environment);self._state="NEW"
    def _abort(self):
        self._state="ABORTED";raise ValueError("RECOVERY_POLICY_REJECTED")
    def preview(self):
        if self._state!="NEW":self._abort()
        self._state="PREVIEWED";return preview(self.plan.signer)
    def confirm(self,signer,*,nonce):
        # This transition is not a substitute for a future interactive user prompt.
        if self._state!="PREVIEWED" or signer!=self.plan.signer or type(nonce) is not int or nonce!=0:self._abort()
        self._state="CONFIRMED"
    def permit(self,method,url):
        if method!="GET":self._abort()
        if self._state=="CONFIRMED" and url==TIME:self._state="TIME_SENT";return
        if self._state=="TIME_VALIDATED" and url==DERIVE:self._state="DERIVE_SPENT";return
        self._abort()
    def time_result(self,status,server_seconds,local_seconds):
        if self._state!="TIME_SENT" or type(status) is not int or status!=200:self._abort()
        if type(server_seconds) is not int or type(local_seconds) is not int or abs(server_seconds-local_seconds)>5:self._abort()
        self._state="TIME_VALIDATED"
    def derive_result(self,status):
        if self._state!="DERIVE_SPENT" or type(status) is not int or status!=200:self._abort()
        self._state="FINISHED"
