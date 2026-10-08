import json

with open(r"D:\polymarket-real-calibration\live\multi-v1-run0242.jsonl") as f:
    for line in f:
        rec = json.loads(line)
        k = rec.get("kind", "")
        if k == "ACK_RESPONSE":
            p = rec.get("payload", {})
            r = p.get("response", {})
            er = r.get("exchange_raw", {})
            client = p.get("client_id", "")
            print(f"{k}: {client}")
            print(f"  makingAmount={er.get('makingAmount')}  takingAmount={er.get('takingAmount')}")
            print(f"  status={r.get('status')}  ok={r.get('ok')}")
            print()
