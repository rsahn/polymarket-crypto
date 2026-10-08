import json

# Check run0241 for actual ORDER events vs SEND_DISPATCH_INTENT
with open(r'D:\polymarket-real-calibration\live\multi-v1-run0241.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        k = d.get('kind','')
        if k in ('ORDER','FILL','TRADE','MULTI_ORDER','MULTI_FILL','REJECTED','CANCEL','HALT','FATAL'):
            pl = json.dumps(d.get("payload",{}))
            print(f'seq={d.get("seq")} kind={k} payload={pl[:500]}')

print('---')
# Also check how many SEND_DISPATCH_INTENT have socket_send_proven=true vs false
true_count = 0
false_count = 0
with open(r'D:\polymarket-real-calibration\live\multi-v1-run0241.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        if d.get('kind') == 'SEND_DISPATCH_INTENT':
            if d.get('payload',{}).get('socket_send_proven') == True:
                true_count += 1
            else:
                false_count += 1

print(f'SEND_DISPATCH_INTENT proven=true: {true_count}, proven=false: {false_count}')

# Check if there are any OPPORTUNITY_COMPLETE events
complete_count = 0
with open(r'D:\polymarket-real-calibration\live\multi-v1-run0241.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        if d.get('kind') == 'OPPORTUNITY_COMPLETE':
            complete_count += 1
print(f'OPPORTUNITY_COMPLETE count: {complete_count}')

# Check the last 50 events to see current state
print('\n=== LAST 50 EVENTS ===')
lines = []
with open(r'D:\polymarket-real-calibration\live\multi-v1-run0241.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        lines.append(line)
for line in lines[-50:]:
    d = json.loads(line)
    k = d.get('kind','')
    pl = json.dumps(d.get("payload",{}))
    print(f'seq={d.get("seq")} kind={k} payload={pl[:300]}')
