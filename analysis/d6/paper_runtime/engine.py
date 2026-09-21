"""Pure virtual execution: no network, wallet, signing or real order client."""
from __future__ import annotations
from decimal import Decimal,ROUND_UP
from collections import deque
from dataclasses import dataclass,asdict
import hashlib,json,math,os
D=lambda x:Decimal(str(x))
ZERO=D(0)
def serial(x):
 if isinstance(x,Decimal):return str(x)
 if hasattr(x,'__dataclass_fields__'):return asdict(x)
 raise TypeError(type(x).__name__)
def encode(x):return json.dumps(x,default=serial,sort_keys=True,separators=(',',':'),allow_nan=False)
def guard(config=None):
 config=os.environ if config is None else config
 for key in ('LIVE_TRADING','ENABLE_LIVE_TRADING','REAL_TRADING','SEND_REAL_ORDERS'):
  if str(config.get(key,'false')).strip().lower() not in ('','0','false','no','off'):raise RuntimeError('REAL_TRADING_FORBIDDEN:'+key)
 for key in ('MODE','TRADING_MODE','D6_MODE'):
  if str(config.get(key,'PAPER')).upper() not in ('PAPER','SHADOW'):raise RuntimeError('PAPER_ONLY:'+key)
@dataclass(frozen=True)
class Limits:
 capital:str='500';cash_reserve:str='100';max_market_cost:str='50';max_order_qty:str='5';max_directional_shares:str='20';max_drawdown:str='25';minimum_depth:str='5';latency_ms:int=250;fresh_ms:int=1000;action_interval_ms:int=3000;fee_rate:str='0.07'
@dataclass
class Position:
 up:Decimal=ZERO;down:Decimal=ZERO;up_cost:Decimal=ZERO;down_cost:Decimal=ZERO;realized:Decimal=ZERO;settled:bool=False
 def state(self):
  paired=min(self.up,self.down)
  return {'up_qty':self.up,'down_qty':self.down,'up_cost':self.up_cost,'down_cost':self.down_cost,'average_up_cost':self.up_cost/self.up if self.up else None,'average_down_cost':self.down_cost/self.down if self.down else None,'paired_qty':paired,'average_pair_cost':self.up_cost/self.up+self.down_cost/self.down if paired else None,'directional_up':max(ZERO,self.up-self.down),'directional_down':max(ZERO,self.down-self.up),'realized_pnl':self.realized,'settled':self.settled}
class Engine:
 def __init__(self,limits=None,journal=None):
  guard();self.limits=limits or Limits();self.cash=D(self.limits.capital);self.reserved=ZERO
  if self.cash!=500 or self.limits.latency_ms<0:raise ValueError('INVALID_PAPER_CONFIG')
  self.positions={};self.identities={};self.books={};self.liquidity={};self.pending=None;self.last_action={};self.sequence=0;self.journal=journal or (lambda row:None)
  self.orders=[];self.fills=[];self.fees=ZERO;self.turnover=ZERO;self.slippage=ZERO;self.peak=self.cash;self.maxdd=ZERO;self.last_features={};self.status='PREPARED';self.reason='NOT_STARTED';self.settlements=set();self.btc=deque();self.last_now=None;self.traded=set();self.max_directional=ZERO;self.time_unhedged_ms=0;self.metric_clock=None;self.metric_unhedged=False;self.market_realized={}
 def emit(self,kind,now,identity=None,**data):
  self.sequence+=1;row={'sequence':self.sequence,'timestamp_ms':now,'kind':kind,'market_slug':identity.get('market_slug') if identity else None,'condition_id':identity.get('condition_id') if identity else None,**data};self.journal(row);return row
 def tick(self,price,source,received,available):
  if not math.isfinite(float(price)) or float(price)<=0:raise ValueError('INVALID_BTC')
  self.btc.append((int(available),int(received),int(source),float(price)))
  while self.btc and self.btc[0][0]<available-65000:self.btc.popleft()
 def observe(self,identity,snapshot,available):
  key=identity['condition_id'];old=self.identities.get(key)
  if old and old!=identity:raise ValueError('CROSS_MARKET_IDENTITY_CHANGED')
  for k,v in identity.items():
   if snapshot.get(k)!=v:raise ValueError('CROSS_MARKET_BOOK')
  if available>=identity['expiry_ts_ms']:return False
  prior=self.books.get(key)
  if prior and snapshot['received_ts_ms']<prior[1]['received_ts_ms']:return False
  for side in ('UP','DOWN'):
   q=snapshot[side.lower()];token=identity['token_'+side.lower()]
   if q['token_id']!=token:raise ValueError('CROSS_MARKET_TOKEN')
   for ladder in ('asks','bids'):
    levels=q.get(ladder,[]);visible={}
    for price,qty in levels:
     p,n=D(price),D(qty)
     if not p.is_finite() or not n.is_finite() or not ZERO<p<D(1) or n<0:raise ValueError('INVALID_DEPTH')
     visible[p]=visible.get(p,ZERO)+n
    previous=self.liquidity.get((token,ladder),{})
    self.liquidity[token,ladder]={p:(n,min(n,previous[p][1]+max(ZERO,n-previous[p][0]))) if p in previous else (n,n) for p,n in visible.items()}
  self.identities[key]=dict(identity);self.positions.setdefault(key,Position());self.books[key]=(available,snapshot);return True
 def admissible(self,key,now):
  if key not in self.books:return False
  available,book=self.books[key];identity=self.identities[key]
  if now>=identity['expiry_ts_ms'] or now<identity['expiry_ts_ms']-(300000 if identity['market_duration']=='5m' else 900000) or self.positions[key].settled:return False
  times=[available,book.get('event_ts_ms'),book.get('received_ts_ms')]
  for side in ('up','down'):times.extend([book[side].get('event_ts_ms'),book[side].get('received_ts_ms',book['received_ts_ms'])])
  return all(t is not None and 0<=now-t<=self.limits.fresh_ms for t in times)
 def features(self,key,now):
  if not self.admissible(key,now):return None
  ticks=[x for x in self.btc if max(x[:3])<=now];latest=ticks[-1] if ticks else None
  if not latest or max(now-x for x in latest[:3])>self.limits.fresh_ms:return None
  f={'btc_price':latest[3],'btc_age_ms':now-latest[1],'btc_provenance':{'available_ms':latest[0],'received_ms':latest[1],'source_ms':latest[2]},'btc_lag_provenance':{}}
  for lag in (250,500,1000,3000,5000,10000,15000,30000):
   old=next((x for x in reversed(ticks) if max(x[:3])<=now-lag),None)
   f['btc_return_'+str(lag)]=latest[3]/old[3]-1 if old and now-lag-min(old[:3])<=1000 else None
   f['btc_lag_provenance'][str(lag)]=list(old) if f['btc_return_'+str(lag)] is not None else None
  prices=[x[3] for x in ticks if now-x[0]<=30000];returns=[math.log(b/a) for a,b in zip(prices,prices[1:])]
  f['volatility']=math.sqrt(sum(x*x for x in returns)/len(returns)) if returns else None
  f['momentum']=f['btc_return_5000'];f['acceleration']=f['btc_return_1000']-f['btc_return_5000']/5 if f['btc_return_1000'] is not None and f['btc_return_5000'] is not None else None
  book=self.books[key][1];p=self.positions[key]
  for side in ('up','down'):
   b=book[side];bid=D(b['bid']) if b.get('bid') is not None else None;ask=D(b['ask']) if b.get('ask') is not None else None
   bidqty=sum(D(x[1]) for x in b.get('bids',[]));askqty=sum(D(x[1]) for x in b.get('asks',[]))
   f.update({side+'_bid':bid,side+'_ask':ask,side+'_depth':askqty,side+'_bid_depth':bidqty,side+'_spread':ask-bid if ask is not None and bid is not None else None,side+'_imbalance':(bidqty-askqty)/(bidqty+askqty) if bidqty+askqty else ZERO})
  f['pair_ask_cost']=f['up_ask']+f['down_ask'] if f['up_ask'] is not None and f['down_ask'] is not None else None
  f['remaining_seconds']=(self.identities[key]['expiry_ts_ms']-now)/1000;f['market_age_seconds']=300-f['remaining_seconds'];f.update(p.state());f['cash']=self.cash;f['inventory_imbalance']=(p.up-p.down)/(p.up+p.down) if p.up+p.down else ZERO
  return f
 def decide(self,key,now):
  f=self.features(key,now)
  if not f:return {'action':'WAIT','reason':'STALE_OR_INSUFFICIENT_CAUSAL_DATA','features':None}
  self.last_features=f
  if self.pending:return {'action':'WAIT','reason':'ORDER_IN_FLIGHT','features':f}
  if now-self.last_action.get(key,-10**12)<self.limits.action_interval_ms:return {'action':'WAIT','reason':'COOLDOWN','features':f}
  if f['momentum'] is None:return {'action':'WAIT','reason':'BTC_WARMUP','features':f}
  momentum=max(-1.,min(1.,f['momentum']*10000/3));micro=float(f['up_imbalance']-f['down_imbalance'])/2;inventory=-float(f['inventory_imbalance'])
  pair=max(-1.,min(1.,float(1-f['pair_ask_cost'])*20))*inventory if f['pair_ask_cost'] is not None else 0.;score=.4*momentum+.3*micro+.2*inventory+.1*pair
  action='WAIT';reason='SIGNAL_BELOW_FIXED_THRESHOLD';side='UP' if score>0 else 'DOWN'
  if abs(score)>=.25:
   action='BUY_'+side;reason='FIXED_CAUSAL_SCORE'
   if f[side.lower()+'_spread'] is None or f[side.lower()+'_spread']>D('.04') or f[side.lower()+'_depth']<D(self.limits.minimum_depth):action='WAIT';reason='LIQUIDITY_FILTER'
   opposite='DOWN' if side=='UP' else 'UP'
   if action!='WAIT' and getattr(self.positions[key],opposite.lower())>0:action='REDUCE_'+opposite;reason='OPPOSITE_SIGNAL_REDUCTION'
  return {'action':action,'reason':reason,'features':f,'internal_score':score,'signals':{'momentum':momentum,'microstructure':micro,'inventory':inventory,'pair_cost':pair}}
 def submit(self,key,decision,now,qty=None):
  if self.pending and decision['action']!='WAIT':raise ValueError('ORDER_ALREADY_PENDING')
  action=decision['action'];identity=self.identities[key];before=self.state(now)
  if action=='WAIT':self.emit('DECISION',now,identity,decision=decision,book_used=self.books.get(key),state_before=before,state_after=before);return None
  if action not in ('BUY_UP','BUY_DOWN','REDUCE_UP','REDUCE_DOWN'):raise ValueError('UNKNOWN_PAPER_ACTION')
  q=min(D(qty if qty is not None else self.limits.max_order_qty),D(self.limits.max_order_qty));side=action.rsplit('_',1)[1]
  if q<=0:raise ValueError('INVALID_QUANTITY')
  if not self.admissible(key,now):return None
  if action.startswith('BUY'):
   reserve=q*(1+D(self.limits.fee_rate)/4)
   if self.cash-reserve<D(self.limits.cash_reserve):return None
   self.reserved=reserve
  else:q=min(q,getattr(self.positions[key],side.lower()));reserve=ZERO
  if q<=0:return None
  order={'decision_id':self.sequence+1,'condition_id':key,'market_slug':identity['market_slug'],'token_id':identity['token_'+side.lower()],'action':action,'requested_qty':q,'filled_qty':ZERO,'submitted_ms':now,'arrival_ms':now+self.limits.latency_ms,'status':'PENDING','reserved':reserve,'features':decision.get('features'),'decision_reason':decision['reason']}
  self.pending=order;self.orders.append(order);self.last_action[key]=now
  self.emit('PAPER_ORDER',now,identity,decision_id=order['decision_id'],decision=decision,book_used=self.books.get(key),state_before=before,order=dict(order),state_after=self.state(now));return order
 def execute_due(self,now):
  order=self.pending
  if not order or now<order['arrival_ms']:return
  key=order['condition_id'];identity=self.identities[key];side=order['action'].rsplit('_',1)[1];buy=order['action'].startswith('BUY');ladder='asks' if buy else 'bids'
  before=self.state(now);parts=[];notional=fee_total=order_slippage=ZERO
  if self.admissible(key,now):
   token=order['token_id'];levels=self.liquidity[token,ladder];best=min(levels) if buy and levels else max(levels) if levels else ZERO
   for price in sorted(levels,reverse=not buy):
    visible,available=levels[price];remaining=order['requested_qty']-order['filled_qty'];q=min(available,remaining);pos=self.positions[key]
    if q<=0:continue
    fee_per=D(self.limits.fee_rate)*price*(1-price)
    if buy:
     affordable=max(ZERO,(self.cash-D(self.limits.cash_reserve))/(price+fee_per))
     cap=max(ZERO,(D(self.limits.max_market_cost)-pos.up_cost-pos.down_cost)/(price+fee_per))
     signed=pos.up-pos.down if side=='UP' else pos.down-pos.up
     q=min(q,affordable,cap,max(ZERO,D(self.limits.max_directional_shares)-signed))
    else:q=min(q,getattr(pos,side.lower()))
    q=q.quantize(D('.000001'),rounding='ROUND_DOWN')
    if q<=0:continue
    fee=(q*fee_per).quantize(D('.00001'),rounding=ROUND_UP);cost=q*price
    if buy and (self.cash-cost-fee<D(self.limits.cash_reserve) or pos.up_cost+pos.down_cost+cost+fee>D(self.limits.max_market_cost)):continue
    oldqty=getattr(pos,side.lower());oldcost=getattr(pos,side.lower()+'_cost')
    if buy:self.cash-=cost+fee;setattr(pos,side.lower(),oldqty+q);setattr(pos,side.lower()+'_cost',oldcost+cost+fee)
    else:
     released=oldcost*q/oldqty;self.cash+=cost-fee;setattr(pos,side.lower(),oldqty-q);setattr(pos,side.lower()+'_cost',oldcost-released);pos.realized+=cost-fee-released
    levels[price]=(visible,available-q);order['filled_qty']+=q;notional+=cost;fee_total+=fee;self.fees+=fee;self.turnover+=cost;self.slippage+=q*abs(price-best);order_slippage+=q*abs(price-best);self.traded.add(key)
    fill={'decision_id':order['decision_id'],'timestamp_ms':now,'condition_id':key,'market_slug':identity['market_slug'],'token_id':token,'action':order['action'],'qty':q,'price':price,'notional':cost,'fees':fee};self.fills.append(fill);parts.append(fill)
  self.reserved=ZERO;self.pending=None;order.update(status='FILLED' if order['filled_qty']==order['requested_qty'] else 'PARTIAL' if parts else 'NO_FILL',vwap=notional/order['filled_qty'] if parts else None,notional=notional,fees=fee_total,slippage=order_slippage,executed_ms=now,observed_latency_ms=now-order['submitted_ms'])
  self.emit('EXECUTION',now,identity,decision_id=order['decision_id'],state_before=before,order=dict(order),fills=parts,book_used=self.books.get(key),state_after=self.state(now))
  if self.cash<0 or any(p.up<0 or p.down<0 for p in self.positions.values()):raise RuntimeError('ACCOUNTING_INVARIANT')
 def settle(self,key,winner,now,evidence):
  identity=self.identities[key]
  if now<identity['expiry_ts_ms'] or winner not in ('UP','DOWN') or evidence.get('condition_id')!=key or evidence.get('resolved') is not True:raise ValueError('UNVERIFIED_SETTLEMENT')
  if key in self.settlements:raise ValueError('DUPLICATE_SETTLEMENT')
  p=self.positions[key];payout=p.up if winner=='UP' else p.down;self.cash+=payout;p.realized+=payout-p.up_cost-p.down_cost;p.up=p.down=p.up_cost=p.down_cost=ZERO;p.settled=True;self.settlements.add(key)
  self.emit('SETTLEMENT',now,identity,winner=winner,payout=payout,evidence=evidence,state_after=self.state(now))
 def state(self,now):
  if self.cash<0 or self.reserved<0 or any(min(p.up,p.down,p.up_cost,p.down_cost)<0 for p in self.positions.values()):raise RuntimeError('ACCOUNTING_INVARIANT')
  exposure=max((abs(p.up-p.down) for p in self.positions.values()),default=ZERO)
  if self.metric_clock is not None and now>=self.metric_clock and self.metric_unhedged:self.time_unhedged_ms+=now-self.metric_clock
  if self.metric_clock is None or now>=self.metric_clock:self.metric_clock=now;self.metric_unhedged=exposure>0
  self.max_directional=max(self.max_directional,exposure)
  value=ZERO;unknown=False
  for key,p in self.positions.items():
   if not(p.up or p.down):continue
   if self.admissible(key,now):
    _,book=self.books[key]
    for side,qty in (('UP',p.up),('DOWN',p.down)):
     remaining=qty;token=self.identities[key]['token_'+side.lower()]
     for price,(_,available) in sorted(self.liquidity.get((token,'bids'),{}).items(),reverse=True):
      q=min(remaining,available);value+=q*price-(q*D(self.limits.fee_rate)*price*(1-price)).quantize(D('.00001'),rounding=ROUND_UP);remaining-=q
      if remaining<=0:break
     if remaining>0:unknown=True
   else:value+=min(p.up,p.down);unknown=unknown or p.up!=p.down
  equity=self.cash+value;self.peak=max(self.peak,equity);dd=self.peak-equity;self.maxdd=max(self.maxdd,dd)
  realized=sum((p.realized for p in self.positions.values()),ZERO)
  settled={k:p.realized for k,p in self.positions.items() if p.settled and k in self.traded}
  winners=sum(v>0 for v in settled.values());losers=sum(v<0 for v in settled.values())
  completed_orders=[o for o in self.orders if o['status']!='PENDING'];filled_orders=sum(o['filled_qty']>0 for o in completed_orders)
  locked=sum((p.up_cost+p.down_cost for p in self.positions.values()),ZERO)
  paired=sum((min(p.up,p.down) for p in self.positions.values()),ZERO)
  weighted_pair=sum((min(p.up,p.down)*(p.up_cost/p.up+p.down_cost/p.down) for p in self.positions.values() if min(p.up,p.down)>0),ZERO)
  absolute_total=sum((abs(v) for v in settled.values()),ZERO)
  performance={'average_pair_cost':weighted_pair/paired if paired else None,'pnl_concentration_absolute':max((abs(v) for v in settled.values()),default=ZERO)/absolute_total if absolute_total else None,'markets_seen':len(self.identities),'markets_traded':len(self.traded),'winning_markets':winners,'losing_markets':losers,'settled_markets':len(settled),'win_rate':D(winners)/len(settled) if settled else None,'pnl_per_settled_market':settled,'best_market':max(settled,key=settled.get) if settled else None,'worst_market':min(settled,key=settled.get) if settled else None,'average_market_pnl':sum(settled.values(),ZERO)/len(settled) if settled else None,'capital_locked':locked,'capital_utilization':locked/D(500),'fill_rate_orders':D(filled_orders)/len(completed_orders) if completed_orders else None,'max_directional_shares':self.max_directional,'time_unhedged_seconds':self.time_unhedged_ms/1000,'realized_pnl':realized,'unrealized_pnl':None if unknown else equity-500-realized}
  return {'performance':performance,'mode':'PAPER','real_money':False,'initial_capital':D(500),'cash':self.cash,'reserved_cash':self.reserved,'equity_lower_bound':equity,'equity':None if unknown else equity,'pnl':None if unknown else equity-500,'pnl_lower_bound':equity-500,'valuation_uncertain':unknown,'drawdown_lower_bound_valuation':dd,'max_drawdown_lower_bound_valuation':self.maxdd,'fees':self.fees,'turnover':self.turnover,'slippage':self.slippage,'orders':len(self.orders),'fills':len(self.fills),'positions':{k:p.state() for k,p in self.positions.items()}}
