"""Build an auditable paper-vs-live comparison from journal facts only."""
def compare_execution(*,signal_id,paper,live):
    def n(d,k):return None if d is None or d.get(k) is None else float(d[k])
    pp=n(paper,"pnl");lp=n(live,"pnl");pv=n(paper,"entry_vwap");lv=n(live,"entry_vwap")
    requested=n(live,"requested_shares");filled=n(live,"filled_shares")
    return {"signal_id":signal_id,"paper_pnl":pp,"live_pnl":lp,
      "pnl_gap":None if pp is None or lp is None else lp-pp,
      "edge_capture_ratio":None if pp in (None,0) or lp is None else lp/pp,
      "entry_slippage":None if pv is None or lv is None else lv-pv,
      "fill_ratio":None if requested in (None,0) or filled is None else filled/requested,
      "ack_latency_ms":live.get("ack_latency_ms") if live else None,
      "fees":n(live,"fees")}
