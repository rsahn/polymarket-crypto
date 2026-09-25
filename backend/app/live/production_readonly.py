"""Read-only adapters for inspected polymarket-client 0.11.0.
Never construct/authenticate a wallet or create an order. Caller supplies an already
validated SDK client. Credential-scoped data is not full-wallet flatness evidence.
"""
import asyncio
import time
from decimal import Decimal, InvalidOperation
from copy import deepcopy


def now_ms():return time.time_ns()//1_000_000

def number(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):raise ValueError("INVALID_NUMBER")
    try:value=Decimal(str(value))
    except InvalidOperation:raise ValueError("INVALID_NUMBER") from None
    if not value.is_finite():raise ValueError("INVALID_NUMBER")
    return value

def units(value):
    raw=number(value)
    if raw<0 or raw!=raw.to_integral_value():raise ValueError("INVALID_BASE_UNITS")
    return raw/Decimal(1000000)

def plain(value):
    if isinstance(value,dict):return dict(value)
    if hasattr(value,"model_dump"):return value.model_dump()
    raise ValueError("UNSUPPORTED_MODEL")

def unavailable(reason):return dict(available=False,complete=False,reason=reason)

def fresh(observed,now,limit=500):
    age=number(now)-number(observed)
    return 0<=age<=limit

async def drain(paginator,max_pages=100,max_items=10000):
    rows=[];seen=set()
    for _ in range(max_pages):
        page=await paginator.first_page()
        if type(page.has_more) is not bool or not isinstance(page.items,(list,tuple)):
            raise ValueError("INVALID_PAGE")
        rows.extend(plain(item) for item in page.items)
        if len(rows)>max_items:raise ValueError("TRUNCATED")
        if not page.has_more:return rows
        cursor=page.next_cursor
        if not isinstance(cursor,str) or not cursor or cursor in seen:raise ValueError("INVALID_CURSOR")
        seen.add(cursor);paginator=paginator.from_cursor(cursor)
    raise ValueError("PAGE_LIMIT")


class AccountStateSource:
    def __init__(self,client,*,wallet,spender,clock=now_ms,timeout=5,collateral_symbol=None):
        self.client,self.wallet,self.spender=client,wallet,spender
        self.clock,self.timeout,self.symbol=clock,timeout,collateral_symbol

    async def read(self):
        started=self.clock()
        try:
            async def collect():
                if str(self.client.wallet).lower()!=self.wallet.lower():raise ValueError("WALLET_MISMATCH")
                bal=plain(await self.client.get_balance_allowance(asset_type="COLLATERAL"))
                balance=units(bal["balance"])
                allowances=bal["allowances"]
                if not isinstance(allowances,dict):raise ValueError("ALLOWANCE_UNKNOWN")
                matches=[units(v) for k,v in allowances.items() if k.lower()==self.spender.lower()]
                if len(matches)!=1:raise ValueError("ALLOWANCE_SPENDER_UNKNOWN")
                orders=await drain(self.client.list_open_orders())
                trades=await drain(self.client.list_account_trades())
                ids=[];trade_ids=set()
                for order in orders:
                    if str(order["maker_address"]).lower()!=self.wallet.lower():raise ValueError("ORDER_WALLET_MISMATCH")
                    oid=order["id"]
                    if not isinstance(oid,str) or not oid or oid in ids:raise ValueError("ORDER_DUPLICATE_OR_INVALID")
                    ids.append(oid)
                for trade in trades:
                    tid=trade["id"]
                    if not isinstance(tid,str) or not tid or tid in trade_ids:raise ValueError("TRADE_DUPLICATE_OR_INVALID")
                    trade_ids.add(tid)
                    if trade["status"] not in {"CONFIRMED","FAILED"}:raise ValueError("TRADE_SETTLEMENT_PENDING")
                if not fresh(started,self.clock()):raise ValueError("ACCOUNT_READ_TOO_OLD")
                return dict(available=True,authenticated=True,wallet=self.wallet,observed_ms=started,
                    balance_collateral=str(balance),allowance_collateral=str(matches[0]),collateral_symbol=self.symbol,
                    balance_usdc=str(balance) if self.symbol=="USDC" else None,
                    allowance_usdc=str(matches[0]) if self.symbol=="USDC" else None,
                    open_order_ids=ids,trade_count=len(trades),pagination_complete=True,
                    complete=False,scope="credential",reason="FULL_WALLET_SCOPE_UNPROVEN")
            return await asyncio.wait_for(collect(),self.timeout)
        except Exception as exc:return unavailable(type(exc).__name__)

    async def order(self,order_id):
        try:
            row=plain(await asyncio.wait_for(self.client.get_order(order_id=order_id),self.timeout))
            if row.get("id")!=order_id or str(row.get("maker_address")).lower()!=self.wallet.lower():
                raise ValueError("ORDER_IDENTITY_MISMATCH")
            return dict(available=True,order=row)
        except Exception as exc:return unavailable(type(exc).__name__)


class PositionSource:
    def __init__(self,client,*,wallet,asset_types,clock=now_ms,timeout=5):
        self.client,self.wallet,self.asset_types=client,wallet,dict(asset_types)
        self.clock,self.timeout=clock,timeout

    async def read(self):
        started=self.clock()
        try:
            async def collect():
                if str(self.client.wallet).lower()!=self.wallet.lower():raise ValueError("WALLET_MISMATCH")
                rows=await drain(self.client.list_positions(user=self.wallet,full_history=True,
                    include_archived=True,filter_type="TOKENS",filter_amount=0))
                balances={}
                for row in rows:
                    if str(row["wallet"]).lower()!=self.wallet.lower():raise ValueError("POSITION_WALLET_MISMATCH")
                    token=str(row["asset_id"]);size=number(row["current_size"])
                    if size<0 or token in balances:raise ValueError("INVALID_POSITION")
                    balances[token]=size
                # Check all configured active assets, even when absent from the indexer.
                for token in set(balances)|set(self.asset_types):
                    asset_type=self.asset_types.get(token)
                    if asset_type not in {"CONDITIONAL","CONDITIONAL-V2"}:raise ValueError("ASSET_TYPE_UNKNOWN")
                    bal=plain(await self.client.get_balance_allowance(asset_type=asset_type,token_id=token))
                    held=units(bal["balance"])
                    if token in balances and balances[token]!=held:raise ValueError("INVENTORY_MISMATCH")
                    if token not in balances and held!=0:raise ValueError("INDEXER_MISSING_INVENTORY")
                    balances[token]=held
                if not fresh(started,self.clock()):raise ValueError("POSITIONS_TOO_OLD")
                return dict(available=True,observed_ms=started,balances={k:str(v) for k,v in balances.items()},
                    pagination_complete=True,complete=False,scope="enumerated_assets",
                    reason="GLOBAL_INVENTORY_ATOMICITY_UNPROVEN")
            return await asyncio.wait_for(collect(),self.timeout)
        except Exception as exc:return unavailable(type(exc).__name__)


class BookStateSource:
    def __init__(self,*,clock=now_ms):
        self.clock=clock;self.connected=False;self.generation=None;self.market=None;self.tokens=();self.books={};self.invalid_reason=None
    def connect(self,market,tokens,generation):
        if isinstance(generation,bool) or not isinstance(generation,int) or (self.generation is not None and generation<=self.generation):raise ValueError("GENERATION_REGRESSION")
        if len(tokens)!=2 or len(set(tokens))!=2:raise ValueError("TWO_OUTCOMES_REQUIRED")
        self.market,self.tokens,self.generation=market,tuple(tokens),generation
        self.books={};self.connected=True;self.invalid_reason="RESYNC_INCOMPLETE"
    def disconnect(self):self.connected=False;self.books={};self.invalid_reason="WS_DISCONNECTED"
    def update(self,token,bids,asks,observed_ms,generation):
        if not self.connected or generation!=self.generation or token not in self.tokens:return
        def levels(rows,reverse):
            result=[]
            for price,size in rows:
                p,q=number(price),number(size)
                if not 0<p<1 or q<=0:raise ValueError("INVALID_DEPTH")
                result.append((p,q))
            if len({p for p,q in result})!=len(result):raise ValueError("DUPLICATE_PRICE")
            return sorted(result,reverse=reverse)
        try:
            if not fresh(observed_ms,self.clock()):raise ValueError("STALE_BOOK")
            bid,ask=levels(bids,True),levels(asks,False)
            if bid and ask and bid[0][0]>=ask[0][0]:raise ValueError("CROSSED_BOOK")
            previous=self.books.get(token)
            if previous and observed_ms<previous["observed_ms"]:raise ValueError("BOOK_REGRESSION")
            self.books[token]=dict(bids=bid,asks=ask,observed_ms=observed_ms)
            self.invalid_reason=None if len(self.books)==2 else "RESYNC_INCOMPLETE"
        except Exception as exc:
            self.invalid_reason=exc.args[0] if exc.args and exc.args[0] in {"EMPTY_BOOK","CROSSED_BOOK","STALE_BOOK","BOOK_REGRESSION","INVALID_DEPTH","DUPLICATE_PRICE"} else "INVALID_BOOK"
            self.books={};raise
    def read(self):
        synchronized=self.connected and len(self.books)==2
        is_fresh=synchronized and all(fresh(b["observed_ms"],self.clock()) for b in self.books.values())
        liquid=synchronized and all(b["bids"] and b["asks"] for b in self.books.values())
        ready=synchronized and is_fresh and liquid
        reason="WS_DISCONNECTED" if not self.connected else self.invalid_reason or ("RESYNC_INCOMPLETE" if not synchronized else "STALE_BOOK" if not is_fresh else "EMPTY_BOOK" if not liquid else None)
        return deepcopy(dict(reason=reason,market_eligible=ready,available=ready,connected=self.connected,synchronized=synchronized,fresh=is_fresh,book_synced=ready,market_slug=self.market,
            generation=self.generation,books=self.books,observed_ms=min((b["observed_ms"] for b in self.books.values()),default=None)))


class GeoBlockSource:
    def __init__(self,fetch=None,*,clock=now_ms):self.fetch=fetch or self._fetch;self.clock=clock
    @staticmethod
    async def _fetch():
        import urllib.request,json
        def get():
            request=urllib.request.Request("https://polymarket.com/api/geoblock",headers={"Accept":"application/json"})
            with urllib.request.urlopen(request,timeout=5) as response:return json.load(response)
        return await asyncio.to_thread(get)
    async def read(self):
        started=self.clock()
        try:
            value=await asyncio.wait_for(self.fetch(),5)
            if not isinstance(value,dict) or type(value.get("blocked")) is not bool:return unavailable("GEOBLOCK_UNKNOWN")
            if not fresh(started,self.clock(),60000):return unavailable("GEOBLOCK_STALE")
            return dict(available=True,blocked=value["blocked"],observed_ms=started)
        except Exception as exc:return unavailable(type(exc).__name__)


class SessionRiskSource:
    """Reads a reconciled, fee-inclusive session ledger; paper PnL is not accepted."""
    def __init__(self,ledger_reader,*,clock=now_ms):self.reader=ledger_reader;self.clock=clock
    def read(self):
        try:
            ledger=self.reader()
            if not isinstance(ledger,dict) or ledger.get("reconciled") is not True or ledger.get("mode")!="REAL_CONFIRMED":
                return unavailable("SESSION_LEDGER_UNRECONCILED")
            if not fresh(ledger["observed_ms"],self.clock()):return unavailable("SESSION_RISK_STALE")
            pnl=number(ledger["realized_net_pnl"]);reserved=number(ledger["reserved_usdc"])
            balance=number(ledger["balance_usdc"]);positions=number(ledger["open_positions"])
            if min(reserved,balance,positions)<0 or reserved>balance or positions!=int(positions):raise ValueError("RISK_INVALID")
            if ledger.get("fees_complete") is not True:return unavailable("FEES_UNKNOWN")
            return dict(available=True,observed_ms=ledger["observed_ms"],session_pnl=str(pnl),available_usdc=str(balance-reserved),
                open_positions=int(positions),allow=pnl>Decimal(-25) and positions==0)
        except Exception as exc:return unavailable(type(exc).__name__)
