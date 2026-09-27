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
 pending=set();errors=[]
 def spawn(coro):
  task=asyncio.create_task(coro)
  def done(t):
   if not t.cancelled() and t.exception() is not None:errors.append(type(t.exception()).__name__)
  task.add_done_callback(done);return task
 env={'btc':deque(maxlen=4096),'ledger':types.SimpleNamespace(record_signal=on_signal),'dryrun':None,'staged':None,'pending':pending,'asyncio':types.SimpleNamespace(create_task=spawn)}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),'<REAL_CALIBRATION_V1_BINDING>','exec'),env)
 bound=env['bind'](on_opportunity);bound.update(pending=pending,errors=errors);return bound
