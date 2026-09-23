"""Polymarket authenticated READ-ONLY probe.
Never places, cancels, approves, or signs an order.
Requires official polymarket-client SDK and env credentials.
"""
import os

class PolymarketReadOnly:
    def __init__(self):
        self._client=None
    @staticmethod
    def configured():
        required=("SIGNER_PRIVATE_KEY","POLYMARKET_WALLET_ADDRESS","POLYMARKET_RELAYER_API_KEY","POLYMARKET_RELAYER_API_KEY_ADDRESS")
        return all(os.getenv(k) for k in required)
    async def connect(self):
        if not self.configured():
            return {"status":"NOT_CONFIGURED","wallet":None,"wallet_type":None}
        from polymarket import AsyncSecureClient,RelayerApiKey
        self._client=await AsyncSecureClient.create(
            private_key=os.environ["SIGNER_PRIVATE_KEY"],
            wallet=os.environ["POLYMARKET_WALLET_ADDRESS"],
            api_key=RelayerApiKey(key=os.environ["POLYMARKET_RELAYER_API_KEY"],
                                  address=os.environ["POLYMARKET_RELAYER_API_KEY_ADDRESS"]))
        return {"status":"CONNECTED_READ_ONLY","wallet":str(self._client.wallet),"wallet_type":str(self._client.wallet_type)}
    async def close(self):
        if self._client is not None:
            close=getattr(self._client,"close",None)
            if close is not None:
                r=close()
                if hasattr(r,"__await__"):await r
            self._client=None
