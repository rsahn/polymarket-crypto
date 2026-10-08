"""Full wallet check after accidental trades."""
import asyncio, json, os
from pathlib import Path
from decimal import Decimal
import urllib.request

ROOT = Path(r"C:\Users\Ramy\Documents\polymarket-crypto")
sys_path_setup = str(ROOT)
import sys
sys.path[:0] = [sys_path_setup, sys_path_setup + "/backend"]

from polymarket import AsyncSecureClient, ApiKeyCreds
from polymarket.environments import PRODUCTION, _create_environment, _EnvironmentConfig
from app.live.l2_existing_reader import load_existing
from app.live.production_readonly import AccountStateSource, PositionSource

ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
SIGNER  = "0x9348eFd557A09e644795C8F114BcF0BeF86F203a"
COLLATERAL = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
EXCHANGE_V2 = "0xe2222d279d744050d28e00520010520000310f59"

_PRODUCTION_CONFIG = PRODUCTION._config
PATCHED_ENV = _create_environment(
    name="production",
    config=_EnvironmentConfig(
        chain_id=_PRODUCTION_CONFIG.chain_id,
        wallet_derivation=_PRODUCTION_CONFIG.wallet_derivation,
        collateral_token=_PRODUCTION_CONFIG.collateral_token,
        conditional_tokens=_PRODUCTION_CONFIG.conditional_tokens,
        neg_risk_adapter=_PRODUCTION_CONFIG.neg_risk_adapter,
        collateral_adapter=_PRODUCTION_CONFIG.collateral_adapter,
        neg_risk_collateral_adapter=_PRODUCTION_CONFIG.neg_risk_collateral_adapter,
        standard_exchange=_PRODUCTION_CONFIG.standard_exchange,
        neg_risk_exchange=_PRODUCTION_CONFIG.neg_risk_exchange,
        auto_redeem_operator=_PRODUCTION_CONFIG.auto_redeem_operator,
        safe_multisend=_PRODUCTION_CONFIG.safe_multisend,
        relay_hub=_PRODUCTION_CONFIG.relay_hub,
        clob_url=_PRODUCTION_CONFIG.clob_url,
        clob_market_ws_url=_PRODUCTION_CONFIG.clob_market_ws_url,
        clob_user_ws_url=_PRODUCTION_CONFIG.clob_user_ws_url,
        relayer_url=_PRODUCTION_CONFIG.relayer_url,
        gamma_url=_PRODUCTION_CONFIG.gamma_url,
        data_url=_PRODUCTION_CONFIG.data_url,
        rfq_url=_PRODUCTION_CONFIG.rfq_url,
        rtds_ws_url=_PRODUCTION_CONFIG.rtds_ws_url,
        sports_ws_url=_PRODUCTION_CONFIG.sports_ws_url,
        rpc_url="https://rpc-mainnet.matic.quiknode.pro",
        exchange_v3=_PRODUCTION_CONFIG.exchange_v3,
        protocol_v2_router=_PRODUCTION_CONFIG.protocol_v2_router,
        binary_module=_PRODUCTION_CONFIG.binary_module,
        neg_risk_module=_PRODUCTION_CONFIG.neg_risk_module,
        combinatorial_module=_PRODUCTION_CONFIG.combinatorial_module,
        position_manager=_PRODUCTION_CONFIG.position_manager,
        rfq_quoter_ws_url=_PRODUCTION_CONFIG.rfq_quoter_ws_url,
        builder_gateway_url=_PRODUCTION_CONFIG.builder_gateway_url,
        collateral_return_url=_PRODUCTION_CONFIG.collateral_return_url,
        perps_url=_PRODUCTION_CONFIG.perps_url,
        perps_ws_url=_PRODUCTION_CONFIG.perps_ws_url,
        realtime_ws_url=_PRODUCTION_CONFIG.realtime_ws_url,
        perps_deposit_contract=_PRODUCTION_CONFIG.perps_deposit_contract,
        relayer_max_polls=_PRODUCTION_CONFIG.relayer_max_polls,
        relayer_poll_frequency_ms=_PRODUCTION_CONFIG.relayer_poll_frequency_ms,
    ),
)

async def main():
    creds_dict, report = load_existing(ROOT)
    api_creds = ApiKeyCreds(
        key=creds_dict["apiKey"],
        secret=creds_dict["secret"],
        passphrase=creds_dict["passphrase"],
    )
    
    private_key = None
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().split("\n"):
            line = line.strip()
            if line.startswith("SIGNER_PRIVATE_KEY="):
                val = line.split("=", 1)[1].strip()
                if val: private_key = val; break
    if not private_key:
        for ev in ("SIGNER_PRIVATE_KEY", "D6_PRIVATE_KEY"):
            val = os.environ.get(ev)
            if val: private_key = val; break
    
    client = await AsyncSecureClient.create(
        private_key=private_key, wallet=ACCOUNT,
        environment=PATCHED_ENV, credentials=api_creds, nonce=0,
    )
    
    now_ms = lambda: int(asyncio.get_event_loop().time() * 1000)
    
    # 1. Check account balance
    account_reader = AccountStateSource(
        client, wallet=ACCOUNT, spender=EXCHANGE_V2,
        clock=now_ms, collateral_symbol="pUSD",
    )
    a = await account_reader.read()
    print("=== ACCOUNT BALANCE ===")
    print(f"Balance collateral (pUSD): {a.get('balance_collateral')}")
    print(f"Balance collateral (raw): {a.get('balance_collateral_raw', '?')}")
    print(f"Allowance: {a.get('allowance', '?')}")
    print(f"Open orders: {len(a.get('open_order_ids', []))}")
    print(f"Terminal orders: {len(a.get('terminal_order_ids', []))}")
    print(f"Trade IDs: {len(a.get('trade_ids', []))}")
    
    # 2. Check if we can find the two orders in trade history
    print("\n=== RECENT TRADE IDS ===")
    trade_ids = a.get('trade_ids', [])
    # Show last 5
    for tid in trade_ids[-5:]:
        print(f"  {tid}")
    
    # 3. Try to check positions for XRP and SOL DOWN tokens
    xrp_down = "70568287516634927910080008044038824216080530124730877157743868839897324350088"
    sol_down = "46324346424016376292305340385701365995770314495903160035205443642686506844073"
    
    # Try to get ALL token IDs from recent trade
    print("\n=== CHECKING ALL TOKEN BALANCES ===")
    position_reader = PositionSource(
        client, wallet=ACCOUNT,
        asset_types={
            xrp_down: "CONDITIONAL",
            sol_down: "CONDITIONAL",
        },
        clock=now_ms, collateral_symbol="pUSD",
    )
    p = await position_reader.read()
    print(f"Positions available: {p.get('available')}")
    if p.get('balances'):
        for tok, bal in p['balances'].items():
            short = tok[:20] + "..."
            print(f"  {short}: {bal}")
    
    # 4. Check on-chain balance via RPC
    print("\n=== ON-CHAIN BALANCE ===")
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider("https://rpc-mainnet.matic.quiknode.pro"))
    token_contract = w3.eth.contract(
        address=Web3.to_checksum_address("0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"),
        abi=[{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
    )
    balance_wei = token_contract.functions.balanceOf(Web3.to_checksum_address(ACCOUNT)).call()
    print(f"USDC.e balance (raw): {balance_wei}")
    print(f"USDC.e balance (human): {balance_wei / 1e6:.2f}")
    
    await client.close()

asyncio.run(main())
