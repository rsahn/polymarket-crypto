import asyncio,os
from app.live.polymarket_readonly import PolymarketReadOnly

def test_readonly_without_secrets(monkeypatch):
 for k in ("SIGNER_PRIVATE_KEY","POLYMARKET_WALLET_ADDRESS","POLYMARKET_RELAYER_API_KEY","POLYMARKET_RELAYER_API_KEY_ADDRESS"):
  monkeypatch.delenv(k,raising=False)
 p=PolymarketReadOnly();r=asyncio.run(p.connect())
 assert r["status"]=="NOT_CONFIGURED" and p._client is None
