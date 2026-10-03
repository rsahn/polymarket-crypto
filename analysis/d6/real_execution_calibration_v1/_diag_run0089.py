"""Run0089 journal diagnostic - read-only."""
import json, sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from analysis.d6.real_execution_calibration_v1.core import Journal

path = Path('D:/polymarket-real-calibration/live/live-v1-run0089.jsonl')
rows = list(Journal.read(path))
print(f"Total rows: {len(rows)}")

# Phase 1: Find all events of interest
calib_exceptions = []
stops = []
journal_failures = []
account_failures = []
reconciled_after_stop = []
background_tasks = []
checkpoints = []

for r in rows:
    k, p = r['kind'], r['payload']
    if k == 'CALIBRATION_EXCEPTION':
        calib_exceptions.append(r)
    elif k == 'STOP':
        stops.append(r)
    elif k == 'CHECKPOINT':
        checkpoints.append(r)
    elif k == 'ACCOUNT_MONITOR_FAILURE':
        account_failures.append(r)
    elif k == 'RECONCILED' and stops:
        reconciled_after_stop.append(r)

print(f"\n=== CALIBRATION_EXCEPTION events: {len(calib_exceptions)} ===")
for r in calib_exceptions:
    p = r['payload']
    print(f"  seq={r['seq']}  type={p.get('exception_type')}  msg={str(p.get('message_redacted',''))[:120]}  transient={p.get('transient')}  component={p.get('component')}  recovery={p.get('recovery_attempted')}")

print(f"\n=== STOP events: {len(stops)} ===")
for r in stops:
    p = r['payload']
    print(f"  seq={r['seq']}  reason={p.get('reason')}  details={json.dumps(p.get('details',{}),default=str)[:200]}")

print(f"\n=== ACCOUNT_MONITOR_FAILURE events: {len(account_failures)} ===")
for r in account_failures:
    p = r['payload']
    print(f"  seq={r['seq']}  type={p.get('exception_type')}  msg={str(p.get('message',''))[:120]}  failures={p.get('failures')}  component={p.get('component')}")

# Phase 2: Trace the chain of events before STOP
print(f"\n=== LAST 100 EVENTS BEFORE STOP ===")
last_stop_seq = stops[-1]['seq'] if stops else len(rows)
start = max(0, last_stop_seq - 100)
for r in rows[start:last_stop_seq+1]:
    k, p = r['kind'], r['payload']
    detail = ""
    if k == 'CALIBRATION_EXCEPTION':
        detail = f"  type={p.get('exception_type')}  msg={str(p.get('message_redacted',''))[:100]}  transient={p.get('transient')}"
    elif k == 'STOP':
        detail = f"  reason={p.get('reason')}"
    elif k == 'ACCOUNT_MONITOR_FAILURE':
        detail = f"  type={p.get('exception_type')}  failures={p.get('failures')}"
    elif k == 'RECONCILED':
        detail = f"  reconciled=True"
    elif k == 'RECONCILIATION_OBSERVATION':
        detail = f"  observed"
    elif k == 'WS_RECONNECTED':
        detail = f"  state={p.get('state')}"
    print(f"  seq={r['seq']}  kind={k}{detail}")

# Phase 3: Events after STOP
print(f"\n=== EVENTS AFTER LAST STOP ===")
for r in rows[last_stop_seq+1:]:
    k, p = r['kind'], r['payload']
    detail = ""
    if k in ('RECONCILED','RECONCILIATION_OBSERVATION'):
        detail = f"  reconciled={p.get('CALIBRATION_ACCOUNT_RECONCILED')}"
    elif k == 'CHECKPOINT':
        report = p.get('report',{})
        detail = f"  stop={report.get('STOP_NEW_ENTRIES')}  reasons={report.get('reasons')}"
    print(f"  seq={r['seq']}  kind={k}{detail}")

# Phase 4: Checkpoint analysis
print(f"\n=== CHECKPOINT (last) ===")
if checkpoints:
    r = checkpoints[-1]
    p = r['payload']
    report = p.get('report',{})
    print(json.dumps({
        'seq': r['seq'],
        'arm_persisted': p.get('arm_persisted'),
        'journal_previous': p.get('journal_previous')[:16] + '...',
        'journal_sequence': p.get('journal_sequence'),
        'report': {
            'STOP_NEW_ENTRIES': report.get('STOP_NEW_ENTRIES'),
            'reasons': report.get('reasons'),
            'CALIBRATION_ACCOUNT_RECONCILED': report.get('CALIBRATION_ACCOUNT_RECONCILED'),
            'entries_attempted': report.get('entries_attempted'),
            'orders_attempted': report.get('orders_attempted'),
            'fills': report.get('fills'),
            'cash': report.get('remaining_experiment_budget'),
            'exposure_known': report.get('exposure_known'),
            'positions': report.get('open_exposure'),
        }
    }, indent=2, default=str))

# Phase 5: Count events by kind
from collections import Counter
kind_counts = Counter(r['kind'] for r in rows)
print(f"\n=== EVENT COUNTS ===")
for kind, count in sorted(kind_counts.items(), key=lambda x: -x[1]):
    print(f"  {kind}: {count}")

# Phase 6: Find all unique error/exception events
print(f"\n=== ALL EXCEPTION/ERROR EVENTS ===")
for r in rows:
    k = r['kind']
    if k in ('CALIBRATION_EXCEPTION','ACCOUNT_MONITOR_FAILURE','STOP'):
        continue
    if 'ERROR' in k or 'EXCEPTION' in k or 'FAIL' in k:
        print(f"  seq={r['seq']}  kind={k}  payload={json.dumps(r['payload'],default=str)[:200]}")

# Phase 7: Check for any BTC or V1 diagnostic events
print(f"\n=== BTC/V1/SIGNAL/OPPORTUNITY EVENTS ===")
for r in rows:
    k = r['kind']
    if 'BTC' in k or 'V1' in k or 'SIGNAL' in k or 'OPPORTUNITY' in k or 'TICK' in k:
        print(f"  seq={r['seq']}  kind={k}  payload={json.dumps(r['payload'],default=str)[:150]}")

# Phase 8: Check if any journal failure occurred
print(f"\n=== JOURNAL FAILURE SEARCH ===")
journal_failure_events = [r for r in rows if 'JOURNAL' in r['kind']]
for r in journal_failure_events:
    print(f"  seq={r['seq']}  kind={r['kind']}  payload={json.dumps(r['payload'],default=str)[:200]}")
if not journal_failure_events:
    print("  No JOURNAL_FAILURE event found in journal (expected - it would crash before writing)")

# Phase 9: Verify hash chain integrity
print(f"\n=== JOURNAL INTEGRITY ===")
try:
    Journal.read(path)
    print("  Journal integrity: OK")
except Exception as e:
    print(f"  Journal integrity FAILED: {e}")
