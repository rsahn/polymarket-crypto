def compare_shadow_live(*, signal_id, paper, live):
    pp=paper.get("pnl");lp=live.get("pnl")
    gap=None if pp is None or lp is None else lp-pp
    capture=None if pp in (None,0) or lp is None else lp/pp
    return {"signal_id":signal_id,"paper":paper,"live":live,
            "pnl_gap":gap,"edge_capture_ratio":capture}
