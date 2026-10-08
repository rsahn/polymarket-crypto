"""Simple on-chain balance check via QuikNode."""
from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://rpc-mainnet.matic.quiknode.pro"))

# USDC.e on Polygon
usdc_addr = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
wallet = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"

token = w3.eth.contract(
    address=Web3.to_checksum_address(usdc_addr),
    abi=[{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
)
bal = token.functions.balanceOf(Web3.to_checksum_address(wallet)).call()
print(f"On-chain USDC.e: {bal / 1e6:.2f}")
print(f"Raw: {bal}")

# Also check MATIC for gas
matic_bal = w3.eth.get_balance(Web3.to_checksum_address(wallet))
print(f"MATIC: {matic_bal / 1e18:.4f}")
