import json, urllib.request

# Check wallet balance and activity on Polygon via QuikNode RPC
rpc_url = "https://rpc-mainnet.matic.quiknode.pro"
wallet = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
pUsd = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"

# 1. Get MATIC balance
payload = json.dumps({
    "jsonrpc": "2.0",
    "method": "eth_getBalance",
    "params": [wallet, "latest"],
    "id": 1
}).encode()
req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
matic_wei = int(resp.get("result", "0x0"), 16)
print(f"MATIC balance: {matic_wei / 10**18:.6f} MATIC")

# 2. Get pUSD balance (USDC.e style token)
# ERC20 balanceOf
data = "0x70a08231" + "000000000000000000000000" + wallet[2:].lower()
payload2 = json.dumps({
    "jsonrpc": "2.0",
    "method": "eth_call",
    "params": [{"to": pUsd, "data": data}, "latest"],
    "id": 2
}).encode()
req2 = urllib.request.Request(rpc_url, data=payload2, headers={"Content-Type": "application/json"})
resp2 = json.loads(urllib.request.urlopen(req2, timeout=15).read())
pusd_raw = int(resp2.get("result", "0x0"), 16)
print(f"pUSD balance: {pusd_raw / 10**6:.2f} pUSD")

# 3. Get recent transactions (via eth_getLogs for Transfer events from our wallet to pUSD)
# Transfer event signature: 0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef
# Topics: from = our wallet
from_topics = "0x000000000000000000000000" + wallet[2:].lower()
payload3 = json.dumps({
    "jsonrpc": "2.0",
    "method": "eth_getLogs",
    "params": [{
        "address": pUsd,
        "fromBlock": "0x0",
        "toBlock": "latest",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            from_topics
        ]
    }],
    "id": 3
}).encode()
req3 = urllib.request.Request(rpc_url, data=payload3, headers={"Content-Type": "application/json"})
resp3 = json.loads(urllib.request.urlopen(req3, timeout=15).read())
logs = resp3.get("result", [])
print(f"\npUSD Transfer OUT transactions: {len(logs)}")
for log in logs[-10:]:
    tx_hash = log.get("transactionHash", "?")
    block = log.get("blockNumber", "?")
    value = int(log["data"], 16) / 10**6 if log.get("data") and log["data"] != "0x" else 0
    to_addr = "0x" + log["topics"][2][-40:] if len(log["topics"]) > 2 else "?"
    print(f"  TX: {tx_hash[:20]}...  Block: {block}  Value: {value:.2f} pUSD  To: {to_addr[:20]}...")

# Also check incoming transfers
to_topics = "0x000000000000000000000000" + wallet[2:].lower()
payload4 = json.dumps({
    "jsonrpc": "2.0",
    "method": "eth_getLogs",
    "params": [{
        "address": pUsd,
        "fromBlock": "0x0",
        "toBlock": "latest",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            None,
            to_topics
        ]
    }],
    "id": 4
}).encode()
req4 = urllib.request.Request(rpc_url, data=payload4, headers={"Content-Type": "application/json"})
resp4 = json.loads(urllib.request.urlopen(req4, timeout=15).read())
in_logs = resp4.get("result", [])
print(f"\npUSD Transfer IN transactions: {len(in_logs)}")
total_in = 0
total_out = 0
for log in in_logs[-5:]:
    value = int(log["data"], 16) / 10**6 if log.get("data") and log["data"] != "0x" else 0
    from_addr = "0x" + log["topics"][1][-40:] if len(log["topics"]) > 1 else "?"
    print(f"  From: {from_addr[:20]}...  Value: {value:.2f} pUSD")

# Total in/out
for log in logs:
    total_out += int(log["data"], 16) / 10**6 if log.get("data") and log["data"] != "0x" else 0
for log in in_logs:
    total_in += int(log["data"], 16) / 10**6 if log.get("data") and log["data"] != "0x" else 0
print(f"\nTotal pUSD OUT: {total_out:.2f}")
print(f"Total pUSD IN:  {total_in:.2f}")
print(f"Net: {total_in - total_out:.2f}")
