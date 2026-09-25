"""GET-only SDK-model facade. No secure-client constructor, signer or write API.
Internal SDK parsers are version-pinned; no SDK network transport is constructed.
"""
import asyncio
import json
import time
import urllib.request
import urllib.parse
from types import SimpleNamespace
from importlib.metadata import version
from .production_readonly import BookStateSource, now_ms


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class GetOnlyTransport:
    def __init__(self,base,routes,*,headers=None,audit=None):
        parsed=urllib.parse.urlsplit(base)
        if parsed.scheme!="https" or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError("INVALID_BASE")
        self.base=base.rstrip("/");self.routes=frozenset(routes);self.headers=headers;self.audit=audit if audit is not None else []
    async def get_json(self,path,params=None,headers=None):
        if path not in self.routes:raise ValueError("GET_ROUTE_NOT_ALLOWED")
        supplied=await self.headers(path) if self.headers else {}
        supplied.update(headers or {})
        def read():
            started=now_ms();entry=dict(method="GET",endpoint=self.base+path,started_ms=started)
            try:
                query=urllib.parse.urlencode({k: (str(v).lower() if type(v) is bool else v) for k,v in (params or {}).items()})
                request=urllib.request.Request(self.base+path+("?"+query if query else ""),headers={"User-Agent":"Mozilla/5.0","Accept":"application/json",**supplied},method="GET")
                with urllib.request.build_opener(NoRedirect()).open(request,timeout=8) as response:
                    entry["http_status"]=response.status
                    payload=response.read(4_000_001)
                    if len(payload)>4_000_000:raise ValueError("RESPONSE_LIMIT")
                    value=json.loads(payload)
                    entry["shape"]=type(value).__name__
                    return value
            except Exception as exc:
                entry["error_type"]=type(exc).__name__
                if hasattr(exc,"code"):entry["http_status"]=exc.code
                raise RuntimeError("READ_FAILED") from None
            finally:
                entry["elapsed_ms"]=now_ms()-started
                self.audit.append(entry)
        return await asyncio.to_thread(read)


class ReadOnlyClient:
    def __init__(self,*,wallet,signature_type,clob,data):
        if version("polymarket-client")!="0.11.0":raise ValueError("SDK_VERSION_UNREVIEWED")
        self.wallet,self.signature_type,self.clob,self.data=wallet,signature_type,clob,data
    async def get_balance_allowance(self,**kw):
        from polymarket._internal.actions import account as a
        path,params=a.build_balance_allowance_request(**kw,signature_type=self.signature_type)
        return a.parse_balance_allowance(await self.clob.get_json(path,params=params))
    async def get_order(self,*,order_id):
        from polymarket._internal.actions import account as a
        path,params=a.build_get_order_request(order_id=order_id)
        return a.parse_open_order(await self.clob.get_json(path,params=params))
    def _pages(self,build,parse):
        from polymarket.pagination import AsyncPaginator
        async def fetch(cursor):
            path,params=build(cursor=cursor)
            return parse(await self.clob.get_json(path,params=params))
        return AsyncPaginator(fetch=fetch)
    def list_open_orders(self):
        from polymarket._internal.actions import account as a
        return self._pages(a.build_list_open_orders_request,a.parse_open_orders_page)
    def list_account_trades(self):
        from polymarket._internal.actions import account as a
        return self._pages(a.build_list_account_trades_request,a.parse_account_trades_page)
    def list_positions(self,**kw):
        from polymarket._internal.actions.data import list_positions_spec
        from polymarket._internal.dispatch import async_paginate_keyset
        return async_paginate_keyset(SimpleNamespace(data=self.data),list_positions_spec(**kw),page_size=100)


def qualify_book(rows,*,tokens,condition,slug,now):
    source=BookStateSource(clock=lambda:now)
    try:
        if len(rows)!=2:raise ValueError("BOOK_COUNT")
        source.connect(slug,tokens,1)
        ages=[]
        for token,row in zip(tokens,rows):
            if row["asset_id"]!=token or row["market"]!=condition:raise ValueError("IDENTITY")
            observed=int(row["timestamp"]);ages.append(now-observed)
            source.update(token,[(x["price"],x["size"]) for x in row["bids"]],[(x["price"],x["size"]) for x in row["asks"]],observed,1)
        result=source.read()
        return dict(available=False,book_synced=False,schema_valid=True,snapshot_fresh=result["available"],
            observed_ms=min(int(r["timestamp"]) for r in rows),ages_ms=ages,reason="REST_SNAPSHOTS_NOT_STREAM_SYNCHRONIZED")
    except Exception:return dict(available=False,book_synced=False,schema_valid=False,reason="BOOK_CONTRACT_REJECTED")
