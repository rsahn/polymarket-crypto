"""Generate a first descriptive D6 lead/lag report from a D5.1 database."""
import argparse, json
from pathlib import Path
from d6.lead_lag import load_d5_timelines, event_study, summarize

def main():
    p=argparse.ArgumentParser()
    p.add_argument("db", type=Path)
    p.add_argument("--lookback-ms", type=int, default=250)
    p.add_argument("--threshold-bps", type=float, default=5.0)
    p.add_argument("--cooldown-ms", type=int, default=1000)
    p.add_argument("--out", type=Path)
    a=p.parse_args()
    report={"contract":"D6_DESCRIPTIVE_ONLY","db":str(a.db.resolve()),"lookback_ms":a.lookback_ms,
            "threshold_bps":a.threshold_bps,"cooldown_ms":a.cooldown_ms,"markets":{}}
    for duration in ("5m","15m"):
        btc,poly=load_d5_timelines(a.db,market_duration=duration,side="UP")
        rows=event_study(btc,poly,lookback_ms=a.lookback_ms,threshold=a.threshold_bps/10000,cooldown_ms=a.cooldown_ms)
        report["markets"][duration]={"btc_ticks":len(btc),"poly_quotes":len(poly),
                                     "responses":summarize(rows)}
    text=json.dumps(report,indent=2,sort_keys=True)
    if a.out:
        a.out.write_text(text,encoding="utf-8")
    print(text)

if __name__=="__main__":
    main()
