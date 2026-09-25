"""Read-only initial inventory evidence; never writes execution state or infers FLAT."""
import json
import sqlite3
import hashlib
from pathlib import Path


def read_local_ledger(path):
    public={'configured':bool(path),'readable':False,'session_history_proven':False,'known_assets_count':None}
    assets=set()
    if not path:return public,assets
    try:
        p=Path(path).resolve(strict=True)
        with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            snapshot=db.execute('SELECT value FROM execution_state WHERE id=1').fetchone()
            events=db.execute('SELECT event,value FROM execution_events ORDER BY id')
            count=0
            for event,value in events:
                count+=1
                if count>100000:raise ValueError()
                state=json.loads(value)
                token=state.get('order',{}).get('token_id')
                if token is not None:
                    if not isinstance(token,str) or not token.isdigit() or int(token)>=2**256:raise ValueError()
                    assets.add(token)
            state=json.loads(snapshot[0]) if snapshot else None
            if state:
                token=state.get('order',{}).get('token_id')
                if token is not None:
                    if not isinstance(token,str) or not token.isdigit() or int(token)>=2**256:raise ValueError()
                    assets.add(token)
            public.update(readable=True,event_count=count,snapshot_present=state is not None,
                recovery_pending=state is not None and state.get('phase')!='CLOSED',known_assets_count=len(assets),
                known_assets_digest=hashlib.sha256(json.dumps(sorted(assets)).encode()).hexdigest())
    except Exception:public['reason']='LOCAL_LEDGER_SCHEMA_OR_READ_FAILED'
    return public,assets


def initial_inventory(views,local):
    # Empty credential/index views are observations, never global wallet proof.
    return {'phase':'GENESIS_RECONCILIATION_PENDING','complete':False,'ledger_created':False,
            'remote_views':views,'local_state':local,
            'known_asset_scope':'EXPLICIT_LOCAL_EXECUTION_EVENTS_ONLY',
            'global_coverage_proven':False,
            'blockers':['GLOBAL_ASSET_DISCOVERY_AND_CONDITIONAL_BALANCES_UNPROVEN',
                        'GLOBAL_OPEN_ORDER_SCOPE_UNPROVEN',
                        'SESSION_HISTORY_AND_GENESIS_PROVENANCE_UNPROVEN']+
                        ([] if local.get('readable') else ['AUTHORITATIVE_LOCAL_LEDGER_NOT_AVAILABLE'])}
