"""Offline specification only. Not imported by any production runner.
Inputs are proof summaries; this module makes no network or current-state claim.
"""


def evaluate_anchor(e, *, now):
    result = dict(anchored_valid=False, current_inventory_proven=False,
                  ready_for_arm=False, submit_allowed=False, reason="CONTRACT_SCHEMA_INVALID")

    def reject(reason):
        return {**result, "reason": reason}

    def integer(value):
        return type(value) is int and value >= 0

    def hash_value(value):
        return (isinstance(value, str) and len(value) == 66 and value.startswith("0x")
                and all(c in "0123456789abcdef" for c in value[2:]))

    try:
        if type(e["chain_id"]) is not int or e["chain_id"] != 137:
            return reject("CHAIN_MISMATCH")
        if e["selection_tag"] != "finalized":
            return reject("FINALIZED_SELECTION_REQUIRED")
        b, recheck, cursor = e["anchor"], e["recheck"], e["cursor"]
        if not all(integer(x["number"]) and hash_value(x["hash"]) for x in (b,recheck,cursor)):
            return result
        if not hash_value(cursor["verified_hash"]):return result
        if cursor["hash"] != cursor["verified_hash"]:return reject("CURSOR_REORG")
        if recheck != b:return reject("ANCHOR_REORG")
        if not integer(e["latest_number"]) or e["latest_number"] < b["number"]:
            return reject("HEAD_BEHIND_ANCHOR")
        if cursor["number"] > b["number"]:return reject("CURSOR_AHEAD_OF_ANCHOR")
        expected = cursor["number"] + 1
        if not isinstance(e["ranges"],list):return result
        for pair in e["ranges"]:
            start, end = pair
            if not integer(start) or not integer(end) or start != expected or end < start or end > b["number"]:
                return reject("COVERAGE_GAP_OR_OVERLAP")
            expected = end + 1
        if expected != b["number"] + 1:return reject("COVERAGE_GAP_OR_OVERLAP")
        if e["logs_complete"] is not True or e["balances_at_anchor"] is not True:
            return reject("ANCHOR_SCOPE_INCOMPLETE")
        generation = e["generation"]
        if (not integer(generation) or generation < 1 or e["account_complete"] is not True
            or any(type(e[k]) is not int or e[k] != generation
                   for k in ("inventory_generation","account_generation"))):
            return reject("GENERATION_PARTIAL")
        times = [e[k] for k in ("inventory_observed_ms","account_observed_ms","recheck_observed_ms")]
        if not integer(now) or not all(integer(t) for t in times):return result
        if any(not 0 <= now - t <= 500 for t in times):return reject("GENERATION_STALE_500MS")
        if times != sorted(times):return reject("ACQUISITION_ORDER_INVALID")
        return {**result, "anchored_valid": True, "reason": "POST_ANCHOR_SCOPE_UNPROVEN",
                "scope": "CTF_INVENTORY_AT_B_ONLY", "block_number": b["number"], "block_hash": b["hash"]}
    except (KeyError,TypeError,ValueError,AttributeError):
        return result
