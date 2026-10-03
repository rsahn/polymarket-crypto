"""Bounded exclusive hourly/final artifacts. Null means unproven, never zero."""
import datetime,json,time
from pathlib import Path
from .core import dec,encoded,redact

def comparison(ledger,record):
 op=record['opportunity_id'];h,s=ledger.shadows[op];trade=ledger.trades[op];entry=record['entry'];real_qty=dec(entry['actual_shares']) if entry.get('actual_shares') is not None else None;real_n=dec(entry['actual_notional']) if entry.get('actual_notional') is not None else None;expected=dec(s['expected_quantity']);price=real_n/real_qty if real_qty else None;expected_price=dec(s['expected_vwap'])
 return {'opportunity_id':op,'shadow_sha256':h,'expected_shadow_price':str(expected_price),'real_fill_price':str(price) if price is not None else None,'price_delta':str(price-expected_price) if price is not None else None,'slippage_bps':str((price/expected_price-1)*10000) if price is not None and expected_price else None,'expected_qty':str(expected),'real_qty':str(real_qty) if real_qty is not None else None,'fill_ratio':str(real_qty/expected) if expected and real_qty is not None else None,'expected_fee':s.get('expected_fee'),'actual_fee':{'cash':str(trade['cash_fees']),'outcome_shares':str(trade['share_fees'])},'fee_delta':None,'fee_comparability':'UNQUALIFIED_UNLESS_UNITS_AND_SCOPE_RECONCILED','expected_latency':{'entry_delay_ms':250,'hold_ms':500,'exchange_ack_ms':None},'actual_latency':{'signal_to_send_call_ms':entry['send_call_ms']-s['signal_decision_ts'] if entry.get('send_call_ms') is not None else None,'ack_ms':entry.get('ack_latency_ms')},'expected_residual':ledger.shadows.get(op+':exit',(None,{}))[1].get('expected_residual'),'actual_residual':record.get('residual_at_observation') if record.get('exposure_known') else None,'entry':entry,'exit':record['exit'],'edge_proven':False}

class Reports:
 def __init__(self,directory,ledger,coordinator,clock=time.monotonic):
  self.directory=Path(directory);self.directory.mkdir(exist_ok=True);self.ledger=ledger;self.coordinator=coordinator;self.clock=clock;self.started=clock();self.hour=-1;self.finalized=False;self.used=0
 def write(self,name,data):
  raw=(encoded(redact(data))+'\n').encode()
  if len(raw)>1024**2 or self.used+len(raw)>64*1024**2:self.ledger.halt('REPORT_STORAGE_LIMIT');raise OSError('REPORT_STORAGE_LIMIT')
  with (self.directory/name).open('xb',buffering=0) as f:
   view=memoryview(raw)
   while view:
    n=f.write(view)
    if not n:raise OSError('REPORT_SHORT_WRITE')
    view=view[n:]
   __import__('os').fsync(f.fileno())
  self.used+=len(raw)
 def snapshot(self,reason=None):
  comparisons=[comparison(self.ledger,r) for r in self.coordinator.comparisons]
  def distribution(key):
   x=sorted(float(c[key]) for c in comparisons if c.get(key) is not None)
   return {'n':len(x),'min':min(x) if x else None,'max':max(x) if x else None,'median':x[len(x)//2] if x else None}
  metrics=self.coordinator.v1.get('diagnostics',lambda:{})()
  metrics.update(getattr(self.coordinator,'runtime_counts',{}))
  report=self.ledger.report()
  metrics.update(ORDER_ATTEMPTS=report['orders_attempted'],ACKS=report['orders_accepted'],FILLS=report['fills'],NO_FILLS=report['no_fills'])
  return {**report,'runtime_diagnostics':metrics,'runtime_seconds':self.clock()-self.started,'opportunities':len(self.ledger.shadows),'shadow_vs_real':comparisons,'slippage_distribution':distribution('slippage_bps'),'fill_ratio_distribution':distribution('fill_ratio'),'ack_latency_ms':[c['actual_latency']['ack_ms'] for c in comparisons],'fee_evidence':'Retained normalized and allowed raw FILL_OBSERVATION / ACK_RESPONSE; documented, reported, inferred and locally calculated fields are distinct','all_reconciliation_results':'Immutable journal RECONCILIATION_OBSERVATION / RECONCILED / STOP events','all_anomalies':self.ledger.reasons.copy(),'kill_switch_state':self.coordinator.kill_path.exists(),'stop_reason':reason,'edge_proven':False}
 def hourly(self):
  h=int((self.clock()-self.started)//3600)
  if h<1 or h<=self.hour or self.finalized:return False
  stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');self.write('REAL_CALIBRATION_HOURLY_'+stamp+'.json',self.snapshot());self.hour=h;return True
 def final(self,reason):
  if self.finalized:raise ValueError('FINAL_ALREADY_WRITTEN')
  for i,r in enumerate(self.coordinator.comparisons,1):self.write('REAL_EXECUTION_COMPARISON_'+str(i)+'.json',comparison(self.ledger,r))
  stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');self.write('REAL_EXECUTION_CALIBRATION_FINAL_'+stamp+'.json',self.snapshot(reason));self.finalized=True
