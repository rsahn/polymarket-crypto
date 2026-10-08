import json, glob, re
from datetime import datetime, timezone

# Check runs around 21:00-21:10 CET (19:00-19:10 UTC = 1791313200000-1791313800000 ms epoch)
# 21:00 CET = 19:00 UTC = 68400 seconds since epoch  
# Oct 6 2026 19:00 UTC in ms: let's calculate
target_start = 1791313200000  # ~21:00 CET
target_end = 1791313800000    # ~21:10 CET

print(f"Looking for trades between {datetime.fromtimestamp(target_start/1000, tz=timezone.utc)} and {datetime.fromtimestamp(target_end/1000, tz=timezone.utc)}")
print()

# Search ALL JSONL for ORDER_BOOK_RESPONSE with matched status
for fn in sorted(glob.glob(r'D:\polymarket-real-calibration\live\multi-v1*.jsonl')):
    has = False
    with open(fn) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                d = json.loads(line)
                k = d.get('kind','')
                if k == 'ORDER_BOOK_RESPONSE':
                    resp = d.get('payload',{}).get('response',{})
                    if resp.get('status') == 'matched':
                        client_id = d.get('payload',{}).get('client_id','')
                        taking = resp.get('exchange_raw',{}).get('takingAmount','?')
                        making = resp.get('exchange_raw',{}).get('makingAmount','?')
                        seq = d.get('seq','?')
                        if not has:
                            print(f'=== {fn} ===')
                            has = True
                        print(f'  seq={seq} client={client_id} making=${making} taking={taking}pos')
            except:
                pass

# Also check runs 0239-0241 specifically around the target time
print('\n=== CHECKING RUN0239-0241 TIMESTAMPS ===')
for fn in sorted(glob.glob(r'D:\polymarket-real-calibration\live\multi-v1-run0239*.jsonl') + 
                 glob.glob(r'D:\polymarket-real-calibration\live\multi-v1-run0240*.jsonl') +
                 glob.glob(r'D:\polymarket-real-calibration\live\multi-v1-run0241*.jsonl')):
    print(f'\n--- {fn} ---')
    with open(fn) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                d = json.loads(line)
                k = d.get('kind','')
                if k in ('ORDER_BOOK_RESPONSE', 'MULTI_TRANSIENT', 'STOP', 'HALT', 'FATAL'):
                    seq = d.get('seq','?')
                    pl = d.get('payload',{})
                    if k == 'ORDER_BOOK_RESPONSE':
                        resp = pl.get('response',{})
                        if resp.get('status') == 'matched':
                            print(f'  seq={seq} ORDER_MATCHED taking={resp.get("exchange_raw",{}).get("takingAmount","?")}')
                        elif resp.get('status'):
                            print(f'  seq={seq} ORDER_{resp.get("status")}')
                    elif k == 'MULTI_TRANSIENT':
                        err = pl.get('error','')
                        if 'balance' in err or 'allowance' in err:
                            print(f'  seq={seq} BALANCE_ERROR: {err[:120]}')
                    elif k in ('STOP','HALT','FATAL'):
                        print(f'  seq={seq} {k}: {pl.get("reason","")}')
            except:
                pass
