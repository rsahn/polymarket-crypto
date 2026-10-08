import json, glob

# Check the matched orders in runs 0231-0238 to see ALL entry amounts
print("=== MATCHED ORDERS WITH AMOUNTS ===")
total_making = 0
trade_count = 0
for fn in sorted(glob.glob(r'D:\polymarket-real-calibration\live\multi-v1*.jsonl')):
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
                        making = float(resp.get('exchange_raw',{}).get('makingAmount',0))
                        taking = float(resp.get('exchange_raw',{}).get('takingAmount',0))
                        client = d.get('payload',{}).get('client_id','')
                        trade_count += 1
                        total_making += making
                        print(f"  {client}: making=${making:.2f} taking={taking:.1f}pos")
            except:
                pass

print(f"\nTotal trades: {trade_count}")
print(f"Total entry amount (making): ${total_making:.2f}")

# Also check SEND_DISPATCH_INTENT amounts (orders that were attempted)
print("\n=== SEND_DISPATCH_INTENT amounts (attempted) ===")
total_intent = 0
intent_count = 0
for fn in sorted(glob.glob(r'D:\polymarket-real-calibration\live\multi-v1*.jsonl')):
    with open(fn) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                d = json.loads(line)
                k = d.get('kind','')
                if k == 'SEND_DISPATCH_INTENT':
                    amt = float(d.get('payload',{}).get('entry_amount', 0))
                    if amt > 0:
                        total_intent += amt
                        intent_count += 1
            except:
                pass

print(f"Total dispatch intents: {intent_count}")
print(f"Total intent entry amount: ${total_intent:.2f}")
