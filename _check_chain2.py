import json, urllib.request, os

# Check what happened to the funds
wallet = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
pUsd = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
rpc_url = "https://rpc-mainnet.matic.quiknode.pro"

# 1. Get pUSD balance
data = "0x70a08231" + "000000000000000000000000" + wallet[2:].lower()
payload = json.dumps({
    "jsonrpc": "2.0", "method": "eth_call",
    "params": [{"to": pUsd, "data": data}, "latest"], "id": 1
}).encode()
req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
pusd_raw = int(resp.get("result", "0x0"), 16)
print(f"Wallet pUSD balance: {pusd_raw / 10**6:.2f} pUSD")

# 2. Check recent blocks only (last 100k blocks ~ 2-3 days)
payload3 = json.dumps({
    "jsonrpc": "2.0", "method": "eth_blockNumber",
    "params": [], "id": 1
}).encode()
req3 = urllib.request.Request(rpc_url, data=payload3, headers={"Content-Type": "application/json"})
resp3 = json.loads(urllib.request.urlopen(req3, timeout=15).read())
latest = int(resp3["result"], 16)
from_block = hex(latest - 100000)
print(f"Latest block: {latest}, scanning from {from_block}")

# pUSD Transfer OUT from wallet (recent only)
from_topics = "0x000000000000000000000000" + wallet[2:].lower()
payload4 = json.dumps({
    "jsonrpc": "2.0", "method": "eth_getLogs",
    "params": [{
        "address": pUsd,
        "fromBlock": from_block,
        "toBlock": "latest",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            from_topics
        ]
    }],
    "id": 2
}).encode()
req4 = urllib.request.Request(rpc_url, data=payload4, headers={"Content-Type": "application/json"})
resp4 = json.loads(urllib.request.urlopen(req4, timeout=15).read())
out_logs = resp4.get("result", [])
print(f"\n=== pUSD OUT (last ~3 days): {len(out_logs)} transfers ===")
total_out = 0
for log in out_logs:
    value = int(log["data"], 16) / 10**6 if log.get("data") and log["data"] != "0x" else 0
    to_addr = "0x" + log["topics"][2][-40:] if len(log["topics"]) > 2 else "?"
    tx_hash = log.get("transactionHash", "?")
    block_num = int(log["blockNumber"], 16)
    total_out += value
    print(f"  ${value:.2f} -> {to_addr}  tx={tx_hash[:20]}...  block={block_num}")

# pUSD Transfer IN to wallet
to_topics = "0x000000000000000000000000" + wallet[2:].lower()
payload5 = json.dumps({
    "jsonrpc": "2.0", "method": "eth_getLogs",
    "params": [{
        "address": pUsd,
        "fromBlock": from_block,
        "toBlock": "latest",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            None,
            to_topics
        ]
    }],
    "id": 3
}).encode()
req5 = urllib.request.Request(rpc_url, data=payload5, headers={"Content-Type": "application/json"})
resp5 = json.loads(urllib.request.urlopen(req5, timeout=15).read())
in_logs = resp5.get("result", [])
print(f"\n=== pUSD IN (last ~3 days): {len(in_logs)} transfers ===")
total_in = 0
for log in in_logs:
    value = int(log["data"], 16) / 10**6 if log.get("data") and log["data"] != "0x" else 0
    from_addr = "0x" + log["topics"][1][-40:] if len(log["topics"]) > 1 else "?"
    tx_hash = log.get("transactionHash", "?")
    total_in += value
    print(f"  ${value:.2f} <- {from_addr}  tx={tx_hash[:20]}...")

print(f"\n=== SUMMARY ===")
print(f"Total pUSD OUT: {total_out:.2f}")
print(f"Total pUSD IN:  {total_in:.2f}")
print(f"Net change: {total_in - total_out:.2f}")
print(f"Current on-chain balance: {pusd_raw / 10**6:.2f}")

# 3. Check MATIC transfers too
matic_abi = "0x70a08231" + "000000000000000000000000" + wallet[2:].lower()
payload6 = json.dumps({
    "jsonrpc": "2.0", "method": "eth_getBalance",
    "params": [wallet, "latest"], "id": 4
}).encode()
req6 = urllib.request.Request(rpc_url, data=payload6, headers={"Content-Type": "application/json"})
resp6 = json.loads(urllib.request.urlopen(req6, timeout=15).read())
matic_wei = int(resp6.get("result", "0x0"), 16)
print(f"MATIC: {matic_wei / 10**18:.6f}")
