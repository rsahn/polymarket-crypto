"""Pin and extract existing V1 selection/fill functions without importing its runner."""
import ast,asyncio,copy,hashlib,types
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
EXPECTED={'analysis/d6/paper_live.py':'5d9759024bbb6e51f6ecb73588fdfd73a5b11a01f582555b008b3f3e60a34364','analysis/run_d6_paper_live.py':'a9bd5809ccf1a1d5c363e1abb62fda7eca5925f98c467da5d87d922afabdf405'}
def verify(root=ROOT):
 hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in EXPECTED}
 if hashes!=EXPECTED:raise ValueError('V1_HASH_MISMATCH')
 return hashes

def bind(on_opportunity,on_signal=lambda r:None):
 verify();tree=ast.parse((ROOT/'analysis/run_d6_paper_live.py').read_text());names=('fill','liquidate','on_btc')
 functions=[copy.deepcopy(n) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
 wrapper=ast.parse('def bind(execute_signal):\n last_signal=-10**18\n return None').body[0]
 wrapper.body[-1:]=functions+[ast.parse('return dict(fill=fill,liquidate=liquidate,on_btc=on_btc)').body[0]]
 pending=set();errors=[];failures=[]
 def spawn(coro):
  task=asyncio.create_task(coro)
  def done(t):
   if not t.cancelled() and t.exception() is not None:
    errors.append(type(t.exception()).__name__);failures.append(t.exception())
  task.add_done_callback(done);return task
 env={'btc':deque(maxlen=4096),'ledger':types.SimpleNamespace(record_signal=on_signal),'dryrun':None,'staged':None,'pending':pending,'asyncio':types.SimpleNamespace(create_task=spawn)}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),'<REAL_CALIBRATION_V1_BINDING>','exec'),env)
 bound=env['bind'](on_opportunity)
 original=bound['on_btc'];intervals=deque(maxlen=4096)
 metrics=dict(BTC_TICKS_RECEIVED=0,BTC_TICK_LAST_MS=None,V1_EVALUATIONS=0,V1_PRIOR_FOUND=0,V1_PRIOR_MISSING=0,V1_SIGNALS=0)
 def signal(row):
  metrics['V1_SIGNALS']+=1;on_signal(row)
 env['ledger'].record_signal=signal
 async def observed(tick):
  previous=metrics['BTC_TICK_LAST_MS']
  if previous is not None:intervals.append(tick.recv_ts_ms-previous)
  metrics['BTC_TICKS_RECEIVED']+=1;metrics['BTC_TICK_LAST_MS']=tick.recv_ts_ms
  metrics['V1_EVALUATIONS']+=1
  prior=next((x for x in env['btc'] if x[0]>=tick.recv_ts_ms-250),None)
  metrics['V1_PRIOR_FOUND' if prior is not None and prior[0]<tick.recv_ts_ms else 'V1_PRIOR_MISSING']+=1
  await original(tick)
 def diagnostics():
  values=sorted(intervals)
  return dict(metrics,BTC_TICK_INTERVAL_P50=values[int((len(values)-1)*.50)] if values else None,BTC_TICK_INTERVAL_P95=values[int((len(values)-1)*.95)] if values else None)
 bound.update(on_btc=observed,pending=pending,errors=errors,failures=failures,diagnostics=diagnostics,reset_feed=env['btc'].clear);return bound
