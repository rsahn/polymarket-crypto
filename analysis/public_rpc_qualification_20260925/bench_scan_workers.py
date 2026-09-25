import concurrent.futures as f,json,statistics,time
def value():return '0x89'
def run(executor=None):
    if executor is None:
        with f.ThreadPoolExecutor(max_workers=8) as pool:
            return [x.result() for x in [pool.submit(value) for _ in range(8)]]
    return [x.result() for x in [executor.submit(value) for _ in range(8)]]
out={}
with f.ThreadPoolExecutor(max_workers=8) as persistent:
    run(persistent)
    for name,pool in [('per_scan',None),('persistent',persistent)]:
        samples=[]
        for _ in range(200):
            start=time.perf_counter_ns();assert run(pool)==['0x89']*8
            samples.append((time.perf_counter_ns()-start)/1e6)
        out[name]={'median_ms':statistics.median(samples),'p95_ms':sorted(samples)[189]}
print(json.dumps(out,indent=2))
