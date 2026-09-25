import asyncio,json,subprocess,sys,threading,types,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from app.live.readonly_book_stream import StreamBook
from app.live.latency_trace import diagnose,measured_thread,sync_span
old=types.ModuleType('app.live.baseline_ws')
old.__package__='app.live'
exec(subprocess.check_output(['git','show','1392c9e:backend/app/live/readonly_book_stream.py'],cwd=ROOT,text=True),old.__dict__)
old.StreamBook.ingest=sync_span('ws.ingest')(old.StreamBook.ingest)
async def scenario(cls):
    s=cls('m','c',('a','b'),10000,clock=lambda:1000)
    s.connected_generation()
    for token in ('a','b'):
        s.ingest(dict(event_type='book',market='c',asset_id=token,timestamp='1000',
            bids=[dict(price=str(i/1000),size='1') for i in range(1,100)],
            asks=[dict(price=str(i/1000),size='1') for i in range(900,999)]))
    gate=threading.Event();entered=threading.Event()
    def worker():
        entered.set();gate.wait(10)
        return 7
    task=asyncio.create_task(measured_thread('synthetic.ready_worker',worker))
    await asyncio.sleep(0)
    assert entered.wait(2)
    event=dict(event_type='price_change',market='c',timestamp='1000',
               price_changes=[dict(asset_id='a',side='BUY',price='.05',size='2')])
    gate.set();start=time.perf_counter();cpu=time.thread_time_ns()
    for _ in range(2000):s.ingest(event)
    elapsed=time.perf_counter()-start
    thread_cpu=(time.thread_time_ns()-cpu)/1e6
    assert await task==7
    return dict(synthetic_only=True,events=2000,wall_ms=elapsed*1000,
                thread_cpu_ms=thread_cpu,available=s.read()['available'])
rows=[]
for name,cls in [('HEAD',old.StreamBook),('existing_ws_fix',StreamBook)]*2:
    result=asyncio.run(diagnose(scenario)(cls))
    trace=result.pop('latency_diagnostics')
    worker=next(x for x in trace['events'] if x['kind']=='worker')
    rows.append(dict(variant=name,**result,worker_resume_ms=worker['resume_ms'],
                     worker_ms=worker['worker_ms'],dropped=trace['dropped_events']))
print(json.dumps(rows,indent=2))
