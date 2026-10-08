import json, glob

for fn in sorted(glob.glob(r'D:\polymarket-real-calibration\live\multi-v1*.jsonl')):
    has = False
    with open(fn) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                d = json.loads(line)
                k = d.get('kind','')
                if k in ('ORDER','FILL','TRADE','MULTI_ORDER','MULTI_FILL','SEND_DISPATCH_INTENT','OPPORTUNITY_COMPLETE','REJECTED','CANCEL'):
                    if not has:
                        print(f'=== {fn} ===')
                        has = True
                    pl = json.dumps(d.get("payload",{}))
                    print(f'  seq={d.get("seq")} kind={k} payload={pl[:400]}')
            except:
                pass
    if not has:
        print(f'{fn}: CLEAN (no trades/orders)')
