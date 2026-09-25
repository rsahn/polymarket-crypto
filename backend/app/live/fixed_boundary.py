"""Fixed block coverage is not proof of inventory at a later account observation.

No remote source currently supplies a common post-C completeness watermark.
This evaluator can certify a bounded observation, never current inventory.
"""
import re


def evaluate_boundary(e, *, now):
    result = dict(inventory_through_C_proven=False, boundary_generation_complete=False,
                  current_inventory_proven=False, ready_for_arm=False, submit_allowed=False,
                  scope='IDENTIFIED_CTF_THROUGH_FIXED_C_NOT_CURRENT', reason='BOUNDARY_SCHEMA_INVALID')
    def fail(reason):
        return {**result, 'reason': reason}
    try:
        ints = ('generation', 'cursor_previous', 'anchor_number', 'boundary_number',
                'scan_observed_ms', 'sealed_ms', 'rechecked_ms', 'events_count')
        if type(now) is not int or any(type(e[k]) is not int or e[k] < 0 for k in ints):
            return result
        if e['generation'] < 1 or e.get('finalized_qualified') is not True:
            return fail('FINALIZED_UNPROVEN')
        for k in ('anchor_hash', 'anchor_rechecked_hash', 'boundary_hash', 'boundary_rechecked_hash'):
            if not isinstance(e[k], str) or not re.fullmatch(r'0x[0-9a-f]{64}', e[k]):
                return result
        if not e['cursor_previous'] <= e['anchor_number'] <= e['boundary_number']:
            return fail('CURSOR_BOUNDARY_INCOHERENT')
        if e['anchor_hash'] != e['anchor_rechecked_hash']:
            return fail('ANCHOR_REORG')
        if e['boundary_hash'] != e['boundary_rechecked_hash']:
            return fail('BOUNDARY_REORG')
        for ranges, start, end in ((e['anchor_ranges'], e['cursor_previous']+1, e['anchor_number']),
                                   (e['tail_ranges'], e['anchor_number']+1, e['boundary_number'])):
            expected = start
            for lo, hi in ranges:
                if type(lo) is not int or type(hi) is not int or lo != expected or hi < lo or hi > end:
                    return fail('COVERAGE_GAP_OR_OVERLAP')
                expected = hi+1
            if expected != end+1:
                return fail('COVERAGE_GAP_OR_OVERLAP')
        if e.get('rpc_complete') is not True:
            return fail('RPC_PARTIAL')
        if not isinstance(e['balances'], dict):
            return result
        if any(not isinstance(v, str) or not re.fullmatch(r'[0-9]+', v) for v in e['balances'].values()):
            return result
        if e['events_count'] or any(int(v) for v in e['balances'].values()):
            return fail('RECOVERY_REQUIRED')
        result['inventory_through_C_proven'] = True
        account = e['account']
        if set(account) != {'balance', 'orders', 'trades', 'positions'}:
            return fail('ACCOUNT_GENERATION_PARTIAL')
        if any(p.get('complete') is not True or type(p.get('generation')) is not int
               or p['generation'] != e['generation'] for p in account.values()):
            return fail('ACCOUNT_GENERATION_PARTIAL')
        times = [e['scan_observed_ms'], e['sealed_ms'], e['rechecked_ms']] + [p['observed_ms'] for p in account.values()]
        if any(type(t) is not int or not 0 <= now-t <= 500 for t in times):
            return fail('GENERATION_STALE_500MS')
        if not e['scan_observed_ms'] <= e['sealed_ms'] <= min(p['observed_ms'] for p in account.values()) or e['rechecked_ms'] < e['sealed_ms']:
            return fail('ACQUISITION_ORDER_INVALID')
        return {**result, 'boundary_generation_complete': True,
                'reason': 'POST_BOUNDARY_CURRENT_SCOPE_UNPROVEN'}
    except (KeyError, TypeError, ValueError, AttributeError):
        return result
