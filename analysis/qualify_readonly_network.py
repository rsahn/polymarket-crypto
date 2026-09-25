"""Bounded real-network qualification. Only allowlisted GETs; no secure client.
Credentials and authentication signatures exist only in memory. No raw responses logged.
"""
import asyncio,json,os,sys,time,hashlib,inspect
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from app.live.network_readonly import GetOnlyTransport,ReadOnlyClient,qualify_book
from app.live.production_readonly import AccountStateSource,PositionSource,GeoBlockSource,drain,now_ms
from app.live.readiness import ProductionReadinessCheck
OUT=ROOT/"analysis/network_readonly_20260925"


def local_config():
    allowed={"REAL_ORDERS_ENABLED","LIVE_EXECUTION_ARMED","SIGNER_PRIVATE_KEY","POLYMARKET_PRIVATE_KEY","PRIVATE_KEY","POLYMARKET_WALLET_ADDRESS"}
    result={}
    for line in (ROOT/".env").read_text(encoding="utf-8-sig").splitlines():
        k,sep,v=line.partition("=")
        if sep and k.strip() in allowed:result[k.strip()]=v.strip().strip("\"'")
    for name in ("REAL_ORDERS_ENABLED","LIVE_EXECUTION_ARMED"):
        if result.get(name,"false").lower()!="false" or os.getenv(name,"false").lower()!="false":raise RuntimeError("LIVE_FLAG_NOT_FALSE")
    return result


async def main():
    config=local_config()
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    from polymarket._internal.actions import auth,account
    from polymarket._internal.l1_auth import sign_api_key_auth
    from polymarket._internal.hmac import build_hmac_signature
    from polymarket._internal.wallet import derive_uups_deposit_wallet_address,derive_beacon_deposit_wallet_address
    from polymarket.clients.async_secure import AsyncSecureClient
    audit=[];observations={};views={}
    for name in ("create","_create","_bootstrap_credentials","_ensure_wallet_ready"):
        obj=getattr(AsyncSecureClient,name,None)
        if obj:observations.setdefault("sdk_paths",{})[name]=hashlib.sha256(inspect.getsource(obj).encode()).hexdigest()
    observations["collateral"]={"asset_type":"COLLATERAL","contract":env.collateral_token,"chain_id":env.chain_id,
        "environment_provenance":"installed polymarket-client 0.11.0 PRODUCTION_CONFIG",
        "symbol_documented":"pUSD","decimals_documented":6,"onchain_verified":False,"account_binding_verified":False,
        "documentation":["https://docs.polymarket.com/resources/contracts","https://docs.polymarket.com/concepts/pusd"]}
    public=GetOnlyTransport(env.clob_url,{"/time","/book","/auth/derive-api-key"},audit=audit)
    data=GetOnlyTransport(env.data_url,{"/v2/positions"},audit=audit)
    geohttp=GetOnlyTransport("https://polymarket.com",{"/api/geoblock"},audit=audit)
    geo=GeoBlockSource(lambda:geohttp.get_json("/api/geoblock"))
    views["geo"]=await geo.read();observations["geo"]=views["geo"]
    client=None
    try:
        # Local ClobAuth signature only. Never an order signature or transaction.
        from eth_account import Account
        key=next((config[k] for k in ("SIGNER_PRIVATE_KEY","POLYMARKET_PRIVATE_KEY","PRIVATE_KEY") if config.get(k)),None)
        if key is None:raise ValueError("NO_AUTH_MATERIAL")
        signer=Account.from_key(key);del key
        server=await public.get_json("/time")
        if type(server) is not int or abs(server-int(time.time()))>5:raise ValueError("SERVER_CLOCK")
        signature=sign_api_key_auth(signer,chain_id=env.chain_id,timestamp=server)
        observations["authentication"]={"type":"ClobAuthDomain credential retrieval only","order_signatures":0}
        creds=auth.parse_api_key_creds(await public.get_json("/auth/derive-api-key",headers=auth.build_l1_auth_headers(signature)))
        del signature
        relayer=GetOnlyTransport(env.relayer_url,{"/deployed"},audit=audit)
        wallet=None
        for derive in (derive_uups_deposit_wallet_address,derive_beacon_deposit_wallet_address):
            candidate=derive(signer.address,env.wallet_derivation)
            deployed=await relayer.get_json("/deployed",params={"address":candidate,"type":"WALLET"})
            if type(deployed.get("deployed")) is not bool:raise ValueError("DEPLOYMENT_UNKNOWN")
            if deployed["deployed"]:wallet=candidate;break
        if wallet is None:raise ValueError("NO_EXISTING_DEPOSIT_WALLET")
        observations["wallet"]={"deployed_verified":True,"selection":"SDK default derivation order; GET deployed must be true",
            "configured_address_matches":config.get("POLYMARKET_WALLET_ADDRESS","").lower()==wallet.lower()}
        async def headers(path):
            stamp=int(time.time())
            return {"POLY_ADDRESS":signer.address,"POLY_API_KEY":creds.key,"POLY_PASSPHRASE":creds.passphrase,
                "POLY_TIMESTAMP":str(stamp),"POLY_SIGNATURE":build_hmac_signature(secret=creds.secret,timestamp=stamp,method="GET",path=path,body=None)}
        secure=GetOnlyTransport(env.clob_url,{"/balance-allowance","/data/orders","/data/trades"},headers=headers,audit=audit)
        client=ReadOnlyClient(wallet=wallet,signature_type=3,clob=secure,data=data)
        raw=await client.get_balance_allowance(asset_type="COLLATERAL")
        observations["balance_model"]={"model":type(raw).__name__,"balance_type":type(raw.balance).__name__,"allowance_count":len(raw.allowances),
            "standard_spender_present":env.standard_exchange.lower() in {k.lower() for k in raw.allowances},"units":"raw integer, documented collateral decimals=6; not relabeled USDC"}
        views["account"]=await AccountStateSource(client,wallet=wallet,spender=env.standard_exchange,collateral_symbol=None).read()
        observations["account"]={k:v for k,v in views["account"].items() if k not in {"wallet","open_order_ids"}}
        for name,method in (("orders",client.list_open_orders),("trades",client.list_account_trades)):
            try:
                rows=await asyncio.wait_for(drain(method()),20)
                observations[name]={"count":len(rows),"sdk_models_parsed":True,"pagination_complete":True,"scope":"credential","complete":False}
            except Exception as exc:observations[name]={"available":False,"error_type":type(exc).__name__,"complete":False}
        try:
            rows=await asyncio.wait_for(drain(client.list_positions(user=wallet,full_history=True,include_archived=True,filter_type="TOKENS",filter_amount=0)),20)
            observations["positions_index"]={"count":len(rows),"wallet_matches":all(str(r["wallet"]).lower()==wallet.lower() for r in rows),
                "pagination_complete":True,"unknown_assets":len(rows),"complete":False}
            # No inferred CONDITIONAL/V2 type. Unknown assets must reject comparison.
            views["positions"]=await PositionSource(client,wallet=wallet,asset_types={}).read()
            observations["positions"]=views["positions"]
        except Exception as exc:observations["positions"]={"available":False,"error_type":type(exc).__name__,"complete":False}
    except Exception as exc:
        observations["account_qualification"]={"available":False,"complete":False,"error_type":type(exc).__name__,"reason":"AUTH_OR_WALLET_READ_UNQUALIFIED_NO_CREATION_FALLBACK"}
    try:
        gamma=GetOnlyTransport(env.gamma_url,{"/markets"},audit=audit)
        start=int(time.time())//300*300;slug=f"btc-updown-5m-{start}"
        markets=await gamma.get_json("/markets",params={"slug":slug})
        if not isinstance(markets,list) or len(markets)!=1 or markets[0].get("slug")!=slug:raise ValueError("MARKET_IDENTITY")
        market=markets[0];tokens=market["clobTokenIds"]
        if isinstance(tokens,str):tokens=json.loads(tokens)
        rows=await asyncio.gather(*(public.get_json("/book",params={"token_id":token}) for token in tokens))
        views["book"]=qualify_book(rows,tokens=tokens,condition=market["conditionId"],slug=slug,now=now_ms())
        observations["book"]=views["book"]
        observations["book"]["raw_types"]=[{k:type(r.get(k)).__name__ for k in ("timestamp","asset_id","market","bids","asks")} for r in rows]
    except Exception as exc:observations["book"]={"available":False,"error_type":type(exc).__name__}
    class View:
        def __init__(self,value):self.value=value
        def read(self):return self.value
    report=await ProductionReadinessCheck(**{k:View(v) for k,v in views.items()}).run()
    # Do not persist account IDs, asset lists, headers, auth response or raw payloads.
    report.pop("observations",None)
    report["status"]="REAL_NETWORK_READ_ONLY_QUALIFICATION_NOT_READY"
    report["provenance"]={k:{"source":({"wallet_auth":"account","balance_usdc":"account","allowance_usdc":"account","open_orders":"orders","inventory":"positions","book_freshness":"book","geoblock":"geo"}.get(k,"local or cross-source; unavailable remains false")),"evaluated_ms":now_ms()} for k in report["checks"]}
    report["qualification"]=observations;report["requests"]=audit
    report["safety"]={"network_methods":sorted({r["method"] for r in audit}),"secure_client_constructed":False,"order_signatures":0,"transactions":0,"monetary_sdk_calls":0,"read_only_routes_enforced":True}
    (OUT/"READINESS_NETWORK.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({"requests":len(audit),"checks":report["checks"],"status":report["status"]}))

if __name__=="__main__":asyncio.run(main())
