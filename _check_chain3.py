import json, urllib.request

wallet = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
rpc_url = "https://rpc-mainnet.matic.quiknode.pro"

# 1. pUSD balance
pUsd = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
data = "0x70a08231" + "000000000000000000000000" + wallet[2:].lower()
payload = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":pUsd,"data":data},"latest"],"id":1}).encode()
req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type":"application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
pusd_bal = int(resp.get("result","0x0"),16) / 10**6
print(f"pUSD wallet balance: {pusd_bal:.2f}")

# 2. Check Polymarket CLOB collateral balance (USDC contract)
# The CLOB uses a wrapper - check allowance to the exchange
# Polymarket Exchange proxy on Polygon
exchange = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"  # CtfExchange

# Get pUSD allowance to exchange
data2 = "0xdd62ed3e" + "000000000000000000000000" + wallet[2:].lower() + "000000000000000000000000" + exchange[2:].lower()
payload2 = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":pUsd,"data":data2},"latest"],"id":2}).encode()
req2 = urllib.request.Request(rpc_url, data=payload2, headers={"Content-Type":"application/json"})
resp2 = json.loads(urllib.request.urlopen(req2, timeout=15).read())
allowance = int(resp2.get("result","0x0"),16) / 10**6
print(f"pUSD allowance to CtfExchange: {allowance:.2f}")

# 3. Check ERC1155 balance (Polymarket uses ERC1155 for positions)
# CTF Exchange ERC1155 balanceOf
erc1155_data = "0x00fdd58e" + "000000000000000000000000" + wallet[2:].lower() + "0000000000000000000000000000000000000000000000000000000000000000"
payload3 = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":exchange,"data":erc1155_data},"latest"],"id":3}).encode()
req3 = urllib.request.Request(rpc_url, data=payload3, headers={"Content-Type":"application/json"})
resp3 = json.loads(urllib.request.urlopen(req3, timeout=15).read())
# This checks token ID 0 - just a test

# 4. Check USDC.e balance (the actual stablecoin used for deposits)
usdc_e = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
data4 = "0x70a08231" + "000000000000000000000000" + wallet[2:].lower()
payload4 = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":usdc_e,"data":data4},"latest"],"id":4}).encode()
req4 = urllib.request.Request(rpc_url, data=payload4, headers={"Content-Type":"application/json"})
resp4 = json.loads(urllib.request.urlopen(req4, timeout=15).read())
usdc_bal = int(resp4.get("result","0x0"),16) / 10**6
print(f"USDC.e wallet balance: {usdc_bal:.2f}")

# 5. Try small block range for pUSD transfers out (last 1000 blocks only)
payload5 = json.dumps({"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":5}).encode()
req5 = urllib.request.Request(rpc_url, data=payload5, headers={"Content-Type":"application/json"})
resp5 = json.loads(urllib.request.urlopen(req5, timeout=15).read())
latest = int(resp5["result"],16)
from_block = hex(latest - 1000)
print(f"\nLatest block: {latest}, scanning last 1000 blocks")

from_topics = "0x000000000000000000000000" + wallet[2:].lower()
payload6 = json.dumps({
    "jsonrpc":"2.0","method":"eth_getLogs",
    "params":[{
        "address":pUsd,
        "fromBlock":from_block,
        "toBlock":"latest",
        "topics":["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",from_topics]
    }],
    "id":6
}).encode()
req6 = urllib.request.Request(rpc_url, data=payload6, headers={"Content-Type":"application/json"})
resp6 = json.loads(urllib.request.urlopen(req6, timeout=15).read())
out_logs = resp6.get("result",[])
print(f"pUSD OUT in last 1000 blocks: {len(out_logs)}")
total_out = 0
for log in out_logs:
    value = int(log["data"],16) / 10**6
    to_addr = "0x"+log["topics"][2][-40:]
    tx = log.get("transactionHash","?")
    block = int(log["blockNumber"],16)
    total_out += value
    print(f"  ${value:.2f} -> {to_addr[:20]}... tx={tx[:20]}... block={block}")

# 6. Also check USDC.e transfers (in case deposit was made)
payload7 = json.dumps({
    "jsonrpc":"2.0","method":"eth_getLogs",
    "params":[{
        "address":usdc_e,
        "fromBlock":from_block,
        "toBlock":"latest",
        "topics":["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",from_topics]
    }],
    "id":7
}).encode()
req7 = urllib.request.Request(rpc_url, data=payload7, headers={"Content-Type":"application/json"})
resp7 = json.loads(urllib.request.urlopen(req7, timeout=15).read())
usdc_out = resp7.get("result",[])
print(f"\nUSDC.e OUT in last 1000 blocks: {len(usdc_out)}")
for log in usdc_out:
    value = int(log["data"],16) / 10**6
    to_addr = "0x"+log["topics"][2][-40:]
    tx = log.get("transactionHash","?")
    print(f"  ${value:.2f} -> {to_addr[:20]}... tx={tx[:20]}...")

# 7. Check what exchange/contract received pUSD from us
print(f"\nTotal pUSD out (1000 blocks): {total_out:.2f}")
print(f"\n=== ACCOUNT STATE ===")
print(f"pUSD (wallet):   {pusd_bal:.2f}")
print(f"USDC.e (wallet): {usdc_bal:.2f}")
print(f"Allowance to CtfExchange: {allowance:.2f}")
print(f"MATIC: ~0")
