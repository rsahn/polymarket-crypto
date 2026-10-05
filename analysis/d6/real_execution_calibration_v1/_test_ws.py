"""Quick WS stability test from VPN Portugal."""
import asyncio, json

async def test_ws():
    from polymarket import AsyncPublicClient
    client = AsyncPublicClient()
    ws_url = client._ctx.environment_config.clob_market_ws_url
    print(f'URL: {ws_url}', flush=True)

    import websockets
    async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10, close_timeout=5) as ws:
        condition_id = '0x5832cf26f38ad2418fdcd1f4093a73e5983617dae804c771c5d7c9833ad78563'
        sub = json.dumps({'type':'subscribe','channel':'book','id':condition_id})
        await ws.send(sub)
        print('Sent subscribe', flush=True)

        for i in range(15):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                t = data.get("type", "?")
                ks = list(data.keys())[:5]
                print(f'msg {i+1}: type={t}, keys={ks}', flush=True)
            except asyncio.TimeoutError:
                print(f'msg {i+1}: TIMEOUT', flush=True)
                break
        print('DONE', flush=True)

asyncio.run(test_ws())
