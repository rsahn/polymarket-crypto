import json, glob, re

# Search ALL log files for any mention of order submission, fill, trade
for fn in sorted(glob.glob(r'D:\polymarket-real-calibration\live\*.log') + glob.glob(r'D:\polymarket-real-calibration\live\*.jsonl')):
    try:
        with open(fn, 'r', errors='ignore') as f:
            content = f.read()
    except:
        continue
    
    # Search for order-related keywords
    keywords = ['ORDER_SENT', 'ORDER_CONFIRMED', 'FILL', 'TRADE_EXECUTED', 
                'socket_send_proven=True', 'socket_send_proven":true',
                'MULTI_ORDER', 'MULTI_FILL', 'order_sent', 'order_confirmed',
                'place_order', 'sign_order', 'send_order', 'dispatch_order',
                'matching', 'matched', 'filled']
    
    for kw in keywords:
        if kw in content:
            print(f'=== {fn} === found: {kw}')
            # Show context around matches
            for m in re.finditer(re.escape(kw), content):
                start = max(0, m.start() - 200)
                end = min(len(content), m.end() + 200)
                snippet = content[start:end].replace('\n', ' ').strip()
                print(f'  ...{snippet}...')
                print()
