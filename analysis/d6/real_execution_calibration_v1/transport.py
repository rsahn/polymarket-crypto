"""Prepared SDK port: no constructor, credentials, approvals or monetary calls at import."""
from dataclasses import asdict,is_dataclass
from decimal import Decimal
from .core import dec,redact

class SDKPort:
 """An already configured human-owned client is injected; no allowance recovery wrapper."""
 def __init__(self,client,*,maker,signer,ledger=None,arm=None,qualified=False):
  self.client=client;self.maker=maker;self.signer=signer;self.ledger=ledger;self.arm=arm;self.qualified=qualified;self.sent=set();self.entry_attempts=0;self.entry_committed=Decimal(0)
 async def prepare(self,*,token,side,amount,price,shares):
  if not self.qualified or self.ledger is None or self.arm is None:raise ValueError('SDK_PATH_NOT_QUALIFIED')
  self.arm.check(self.ledger.journal.experiment_id,entry=side=='BUY')
  if self.ledger.active is None or (side=='BUY' and self.ledger.stop):raise ValueError('UNRESERVED_OR_STOPPED')
  kwargs={'token_id':token,'side':side,'order_type':'FAK'}
  if side=='BUY':
   if not 0<dec(amount)<=25:raise ValueError('ENTRY_CAP_25')
   kwargs.update(amount=str(amount),max_price=str(price))
  elif side=='SELL':kwargs.update(shares=str(shares),min_price=str(price))
  else:raise ValueError('SIDE_INVALID')
  # Never place_market_order/place_limit_order: those may recover allowances.
  signed=await self.client.create_market_order(**kwargs)
  validate_signed(signed,token=token,side=side,amount=amount,price=price,shares=shares,maker=self.maker,signer=self.signer)
  return signed
 async def submit_once(self,client_id,signed):
  if not self.qualified or self.ledger is None or self.arm is None or client_id in self.sent:raise ValueError('UNQUALIFIED_OR_DUPLICATE_SEND')
  if self.ledger.journal.failed:raise ValueError('JOURNAL_FAILED_NO_SEND')
  o=self.ledger.orders.get(client_id)
  if o is None or o['order_id'] is not None:raise ValueError('DURABLE_INTENT_REQUIRED')
  self.arm.check(self.ledger.journal.experiment_id,entry=o['side']=='BUY')
  validate_signed(signed,token=o['token'],side=o['side'],amount=o['notional'],price=o['price'],shares=o['shares'],maker=self.maker,signer=self.signer)
  if o['side']=='BUY':
   slot=dec(o['notional'])+self.ledger.trades[o['opportunity_id']]['fee_ceiling']
   if self.ledger.stop or self.ledger.allocated>100 or self.ledger.allocated+slot>100:raise ValueError('TRANSPORT_BUDGET_OR_STOP')
  elif dec(o['shares'])>self.ledger.positions.get(o['token'],Decimal(0)):raise ValueError('TRANSPORT_EXPOSURE_UNPROVEN')
  self.sent.add(client_id)  # a timeout cannot permit a second attempt
  # Use the pinned SDK request codec and raw authenticated HTTP response.
  # Never call the allowance-recovery placement helper.
  from polymarket.clients.async_secure import _post_actions
  path,payload=_post_actions.build_post_order_request(signed,owner_api_key=self.client._ctx.credentials.key)
  raw=await self.client._ctx.secure_clob.post_json(path,json=payload)
  response=_post_actions.parse_order_response(raw)
  if hasattr(response,'model_dump'):return {**redact(response.model_dump(mode='json')),'exchange_raw':redact(raw)}
  if is_dataclass(response):return redact(asdict(response))
  if isinstance(response,dict):return redact(response)
  raise ValueError('SDK_RESPONSE_SCHEMA_UNKNOWN')

def validate_signed(s,*,token,side,amount,price,shares,maker,signer):
 if str(s.token_id)!=str(token) or s.side!=side or str(s.order_type)!='FAK' or s.post_only:raise ValueError('SIGNED_ORDER_IDENTITY')
 if str(s.maker).lower()!=maker.lower():raise ValueError('SIGNED_ACCOUNT_IDENTITY')
 if getattr(s,'signature_type',None)==3:
  if str(s.signer).lower()!=maker.lower() or not verify_deposit_signature(s,signer):raise ValueError('SIGNED_ACCOUNT_IDENTITY')
 elif str(s.signer).lower()!=signer.lower():raise ValueError('SIGNED_ACCOUNT_IDENTITY')
 if type(s.maker_amount) is not int or type(s.taker_amount) is not int or min(s.maker_amount,s.taker_amount)<=0:raise ValueError('SIGNED_AMOUNTS_INVALID')
 m,t=Decimal(s.maker_amount)/1000000,Decimal(s.taker_amount)/1000000
 p=dec(price)
 if side=='BUY':
  if m>25 or m>dec(amount) or m > p*t + Decimal('0.001'):raise ValueError('SIGNED_ENTRY_CAP_OR_PRICE')
 else:
  if m>dec(shares) or t<p*m:raise ValueError('SIGNED_EXIT_CAP_OR_PRICE')
 return {'requested_notional':str(m if side=='BUY' else t),'requested_shares':str(t if side=='BUY' else m),'limit_price':str(p),'side':side,'token':str(token),'order_type':'FAK'}


def verify_deposit_signature(s,owner):
 """Deposit orders name the wallet as signer; recover the actual EOA owner.
 Strictly pinned production domains, including the SDK's complete 1271 trailer.
 Session-key envelopes are deliberately rejected until separately qualified.
 """
 from eth_account import Account
 from eth_account.messages import encode_typed_data
 from polymarket.clients.async_secure import get_environment_config,PRODUCTION
 from polymarket._internal.actions.orders.context import resolve_order_exchange_address
 from polymarket._internal.actions.orders.types import UnsignedOrder
 from polymarket._internal.actions.orders.typed_data import build_order_typed_data,build_order_signature
 from polymarket._internal.protocol import is_v2_position_id
 try:
  config=get_environment_config(PRODUCTION);sig=bytes.fromhex(s.signature.removeprefix('0x'))
  for neg in (False,True):
   u=UnsignedOrder(chain_id=config.chain_id,exchange_address=resolve_order_exchange_address(config,asset_id=s.token_id,neg_risk=neg),protocol_version='3' if is_v2_position_id(s.token_id) else '2',**{k:getattr(s,k) for k in ('builder','expiration','maker','maker_amount','metadata','order_type','salt','side','signature_type','signer','taker_amount','timestamp','token_id')})
   if build_order_signature(u,'0x'+sig[:65].hex())!=s.signature:continue
   if Account.recover_message(encode_typed_data(full_message=build_order_typed_data(u)),signature=sig[:65]).lower()==owner.lower():return True
 except Exception:return False
 return False
