import json, glob, os

# Check what event kinds are in the JSONL files for runs 0231-0238
for fn in sorted(glob.glob(r'D:\polymarket-real-calibration\live\multi-v1-run023*.jsonl')):
    base = os.path.basename(fn)
    kinds = {}
    trade_lines = []
    with open(fn) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                d = json.loads(line)
                k = d.get('kind','')
                kinds[k] = kinds.get(k,0) + 1
                # Check if this kind relates to order/response
                if 'RESPONSE' in k or 'RESP' in k or 'ORDER' in k or 'MATCH' in k or 'FILL' in k or 'TRADE' in k:
                    trade_lines.append((d.get('seq'), k, line[:400]))
            except:
                pass
    
    if any('RESPONSE' in k for k in kinds):
        print(f'\n=== {base} ===')
        print(f'Kinds: {json.dumps(kinds, indent=2)}')
        for seq, kind, line in trade_lines[:5]:
            print(f'  seq={seq} kind={kind}')
            print(f'  {line[:300]}')
            print()
