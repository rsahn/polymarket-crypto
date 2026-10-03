import json, hashlib
from pathlib import Path

baseline_path = Path('D:/polymarket-real-calibration/preparation/BASELINE.json')
if baseline_path.exists():
    bl = json.loads(baseline_path.read_text())
    bl_digest = hashlib.sha256(json.dumps(bl, sort_keys=True, separators=(',',':'), allow_nan=False).encode()).hexdigest()
    print(f'Baseline exists at: {baseline_path}')
    print(f'Baseline digest: {bl_digest}')
    print(f'Keys: {list(bl.keys())}')
    print(f'account: {bl.get("account")}')
    print(f'collateral: {bl.get("collateral")}')
    print(f'trade_ids: {bl.get("trade_ids", [])}')
    print(f'source_digest: {bl.get("source_digest")}')
    print(f'scope: {bl.get("scope")}')
    print(f'atomic_frontier: {bl.get("atomic_frontier")}')
    print(f'payload keys: {list(bl.get("payload", {}).keys())}')
    print(f'payload.trade_ids: {bl.get("payload", {}).get("trade_ids", [])}')
    print(f'payload.collateral: {bl.get("payload", {}).get("collateral")}')
else:
    print('No BASELINE.json found at D:/')
    # Check in workspace
    alt = Path('C:/Users/Ramy/Documents/polymarket-crypto/analysis/d6/real_execution_calibration_v1')
    for f in alt.iterdir():
        if 'baseline' in f.name.lower():
            print(f'Found: {f}')
            print(f.read_text()[:200])
