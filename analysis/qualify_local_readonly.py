"""Manual local GET-only qualification. No private keys, SDK constructors or signing.
Existing L2 credentials may authenticate GETs with HMAC; never created or derived.
"""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from importlib.metadata import version
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.live.network_readonly import GetOnlyTransport,ReadOnlyClient,qualify_book
from app.live.production_readonly import AccountStateSource,PositionSource,drain
from app.live.readiness import ProductionReadinessCheck
FLAGS=("REAL_ORDERS_ENABLED","LIVE_EXECUTION_ARMED")
AUTH=("READONLY_CLOB_API_KEY","READONLY_CLOB_API_SECRET","READONLY_CLOB_API_PASSPHRASE","READONLY_SIGNER_ADDRESS","READONLY_SIGNATURE_TYPE")
ALLOWED=set(FLAGS+AUTH+("POLYMARKET_WALLET_ADDRESS",))
ROUTES={
 "https://clob.polymarket.com":frozenset(("/time","/book","/balance-allowance","/data/orders","/data/trades")),
 "https://gamma-api.polymarket.com":frozenset(("/markets",)),
 "https://data-api.polymarket.com":frozenset(("/v2/positions",)),
 "https://polymarket.com":frozenset(("/api/geoblock",))}


def read_config(path,environ=None):
    environ=os.environ if environ is None else environ
    result={}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            k,sep,v=line.partition("=")
            if sep and k.strip() in ALLOWED:result[k.strip()]=v.strip().strip("\"'")
    for k in ALLOWED:
        if k in FLAGS:
            values=[result.get(k,"false"),environ.get(k,"false")]
            result[k]="false" if all(v.strip().lower()=="false" for v in values) else "INVALID_OR_ENABLED"
        elif environ.get(k):result[k]=environ[k]
    return result


def blocked(reason):return {"status":"BLOCKED","available":False,"complete":False,"reason":reason}


def write_report(path,report):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2,allow_nan=False)


async def qualify(config,*,transport=GetOnlyTransport,clock=None):
    clock=clock or (lambda:time.time_ns()//1_000_000)
    report=await ProductionReadinessCheck(clock=clock).run()
    report.pop("observations",None)
    report.update(status="LOCAL_NETWORK_READ_ONLY_NOT_READY",complete=False,qualification={},requests=[],
        execution_context="MANUAL_TARGET_MACHINE",previous_codex_403_not_generalized=True)
    q=report["qualification"];audit=report["requests"];views={}
    report["flags"]={n:config.get(n,"false").strip().lower() for n in FLAGS}
    report["provenance"]={k:{"source":"local guard or absent source","status":"PASS" if v else "BLOCKED"} for k,v in report["checks"].items()}
    if any(v!="false" for v in report["flags"].values()):
        report["status"]="BLOCKED_LIVE_FLAGS";report["checks"]["live_flags_disabled"]=False
        report["blockers"]=[k for k,v in report["checks"].items() if not v]
        report["provenance"]["live_flags_disabled"]={"source":".env/process preflight","status":"BLOCKED"};return report
    try:sdk=version("polymarket-client")
    except Exception:sdk="UNAVAILABLE"
    report["sdk_version"]=sdk
    if sdk!="0.11.0":report["status"]="BLOCKED_SDK_VERSION";return report
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    q["collateral"]={"status":"CONFIG_ONLY","asset_type":"COLLATERAL","contract":env.collateral_token,"chain_id":env.chain_id,
        "provenance":"installed SDK PRODUCTION_CONFIG","symbol_onchain":None,"decimals_onchain":None,
        "documentation_symbol":"pUSD","documentation_decimals":6,"account_binding_verified":False,
        "documentation":["https://docs.polymarket.com/resources/contracts","https://docs.polymarket.com/concepts/pusd"]}
    def http(base,headers=None):return transport(base,ROUTES[base],headers=headers,audit=audit)
    public=http("https://clob.polymarket.com");data=http("https://data-api.polymarket.com")
    try:
        started=clock();stamp=await public.get_json("/time");received=clock()
        if type(stamp) is not int:raise ValueError()
        # Endpoint seconds have one-second resolution; this is not NTP qualification.
        skew=received-stamp*1000
        q["time"]={"status":"PASS" if abs(skew)<=5000 else "BLOCKED","server_seconds":stamp,"received_ms":received,
            "round_trip_ms":received-started,"coarse_skew_ms":skew,"ntp_qualified":False}
    except Exception:q["time"]=blocked("TIME_GET_OR_SCHEMA_FAILED")
    try:
        started=clock();value=await http("https://polymarket.com").get_json("/api/geoblock")
        if not isinstance(value,dict) or type(value.get("blocked")) is not bool:raise ValueError()
        views["geo"]={"available":True,"blocked":value["blocked"],"observed_ms":started}
        q["geo"]={"status":"PASS","blocked":value["blocked"],"observed_ms":started}
    except Exception:q["geo"]=blocked("GEOBLOCK_GET_OR_SCHEMA_FAILED")
    wallet=config.get("POLYMARKET_WALLET_ADDRESS","")
    wallet_valid=bool(re.fullmatch(r"0x[0-9a-fA-F]{40}",wallet))
    q["wallet"]={"status":"CONFIG_ONLY" if wallet_valid else "BLOCKED","configured_address_valid":wallet_valid,
        "authenticated_binding_verified":False,"reason":"Configured expected address is not proof of account identity; never silently select another wallet"}
    client=None
    missing=[k for k in AUTH if not config.get(k)]
    q["account"]=blocked("EXISTING_L2_CREDENTIALS_OR_VERIFIED_IDENTITY_CONFIG_MISSING; no SDK create/derive/bootstrap fallback")
    q["account"]["missing_fields"]=missing
    if not missing and wallet_valid and q["time"]["status"]=="PASS":
        try:
            signer=config["READONLY_SIGNER_ADDRESS"];sig=config["READONLY_SIGNATURE_TYPE"]
            if not re.fullmatch(r"0x[0-9a-fA-F]{40}",signer) or sig not in ("0","1","2","3"):raise ValueError()
            from polymarket._internal.hmac import build_hmac_signature
            async def headers(path):
                if path not in ("/balance-allowance","/data/orders","/data/trades"):raise ValueError("AUTH_ROUTE")
                stamp=clock()//1000
                return {"POLY_ADDRESS":signer,"POLY_API_KEY":config[AUTH[0]],"POLY_PASSPHRASE":config[AUTH[2]],"POLY_TIMESTAMP":str(stamp),
                    "POLY_SIGNATURE":build_hmac_signature(secret=config[AUTH[1]],timestamp=stamp,method="GET",path=path,body=None)}
            client=ReadOnlyClient(wallet=wallet,signature_type=int(sig),clob=http("https://clob.polymarket.com",headers),data=data)
            # Classify only address relationships deterministically; unknown session identity stays blocked.
            from polymarket._internal.wallet import classify_account,signature_type_for
            identity=classify_account(signer=signer,wallet=wallet,config=env.wallet_derivation)
            if identity.signer_type!="OWNER" or signature_type_for(identity.wallet_type)!=int(sig):raise ValueError()
            q["wallet"]["configured_relationship_matches_sdk"]=True
            q["account"]=await AccountStateSource(client,wallet=wallet,spender=env.standard_exchange,collateral_symbol=None,clock=clock).read()
            views["account"]=dict(q["account"])
            q["account"]={k:v for k,v in q["account"].items() if k not in ("wallet","open_order_ids")}
            q["account"]["status"]="PASS_READ_ONLY" if q["account"].get("available") else "BLOCKED"
        except Exception:
            client=None;q["account"]=blocked("AUTH_IDENTITY_OR_GET_UNQUALIFIED; no fallback")
    for name in ("orders","trades"):
        q[name]=blocked("AUTHENTICATED_CLIENT_UNAVAILABLE")
        if client:
            try:
                method=client.list_open_orders if name=="orders" else client.list_account_trades
                rows=await asyncio.wait_for(drain(method()),20)
                q[name]={"status":"PASS_READ_ONLY","count":len(rows),"sdk_models_parsed":True,"pagination_complete":True,
                    "complete":False,"scope":"credential; full-wallet coverage unproven"}
            except Exception:q[name]=blocked("GET_PAGINATION_OR_SDK_MODEL_REJECTED")
    q["positions"]=blocked("EXPECTED_WALLET_MISSING")
    if wallet_valid:
        try:
            # Public indexer can be checked independently of authenticated credential availability.
            index=ReadOnlyClient(wallet=wallet,signature_type=0,clob=public,data=data)
            rows=await asyncio.wait_for(drain(index.list_positions(user=wallet,full_history=True,include_archived=True,filter_type="TOKENS",filter_amount=0)),20)
            matches=all(str(r["wallet"]).lower()==wallet.lower() for r in rows)
            q["positions"]={"status":"PASS_INDEX_ONLY" if matches else "BLOCKED","count":len(rows),"wallet_matches":matches,
                "pagination_complete":True,"unknown_asset_types":len(rows),"complete":False,"balance_comparison":"BLOCKED: asset types and authenticated balances not established"}
            if client:
                position=await PositionSource(client,wallet=wallet,asset_types={},clock=clock).read()
                views["positions"]=position
                q["positions"]["adapter_available"]=position.get("available",False)
        except Exception:q["positions"]=blocked("INDEX_GET_PAGINATION_OR_MODEL_REJECTED")
    try:
        start=clock()//1000//300*300;slug=f"btc-updown-5m-{start}"
        markets=await http("https://gamma-api.polymarket.com").get_json("/markets",params={"slug":slug})
        if not isinstance(markets,list) or len(markets)!=1 or markets[0].get("slug")!=slug:raise ValueError()
        market=markets[0];tokens=market["clobTokenIds"]
        if isinstance(tokens,str):tokens=json.loads(tokens)
        if not isinstance(tokens,list) or len(tokens)!=2 or len(set(tokens))!=2 or not all(isinstance(t,str) and t.isdigit() for t in tokens):raise ValueError()
        q["discovery"]={"status":"PASS","slug":slug,"outcomes":2,"asset_ids_valid":True}
        rows=await asyncio.gather(*(public.get_json("/book",params={"token_id":token}) for token in tokens))
        views["book"]=qualify_book(rows,tokens=tokens,condition=market["conditionId"],slug=slug,now=clock())
        q["book"]=dict(views["book"])
        q["book"]["status"]="SNAPSHOTS_ONLY_NOT_STREAM_SYNCHRONIZED"
    except Exception:
        q.setdefault("discovery",blocked("CURRENT_BTC_MARKET_UNAVAILABLE"));q["book"]=blocked("BTC_BOOK_GET_OR_CONTRACT_REJECTED")
    class View:
        def __init__(self,value):self.value=value
        def read(self):return self.value
    final=await ProductionReadinessCheck(**{k:View(v) for k,v in views.items()},clock=clock).run()
    for k in ("checks","blockers","ready_for_arm","submit_allowed"):report[k]=final[k]
    for k in report["checks"]:
        source={"wallet_auth":"account","balance_usdc":"account + collateral identity","allowance_usdc":"account + collateral identity","geoblock":"geo",
            "book_freshness":"book: REST cannot prove stream synchronization","account_reconciliation":"account + positions + local recovery, completeness unproven",
            "open_orders":"orders; credential scope only","inventory":"positions; orphan assets not ruled out","local_recovery_state":"no verified local live state supplied",
            "session_risk":"no real reconciled session ledger supplied","transport_lock":"local AST guard","live_flags_disabled":".env and process preflight"}[k]
        report["provenance"][k]={"source":source,"status":"PASS" if report["checks"][k] else "BLOCKED"}
    report["policy"]={"http_methods":["GET"],"routes":{k:sorted(v) for k,v in ROUTES.items()},"credentials":"existing L2 only; GET HMAC in memory",
        "private_keys_loaded":False,"secure_client_constructor_used":False,"complete_requires_global_evidence":True}
    return report


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=ROOT/"READINESS_LOCAL_NETWORK.json")
    args=parser.parse_args()
    if args.output.exists():print("BLOCKED: output exists; preserve or rename it before another run.");return 2
    try:report=asyncio.run(qualify(read_config(ROOT/".env")))
    except Exception:report={"status":"BLOCKED_LOCAL_RUNTIME","complete":False,"ready_for_arm":False,"submit_allowed":False,"reason":"Local dependency or runtime failure; no exception text logged"}
    write_report(args.output,report)
    print("Redacted report written: "+str(args.output));return 0

if __name__=="__main__":raise SystemExit(main())
