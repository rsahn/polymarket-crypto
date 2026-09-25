"""Atomic, scoped D6 genesis and append-only future audit journal; no execution API."""
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from .collateral_onchain import CONTRACT,CTF
from .l2_existing_reader import EXPECTED

LIMITS=['PRE_GENESIS_HISTORY_NOT_GLOBALLY_KNOWN','ORDERS_AND_TRADES_CREDENTIAL_VIEW_ONLY',
        'CTF_AND_INDEXER_ASSET_SCOPE_ONLY','PUBLIC_RPC_ARCHIVE_COMPLETENESS_TRUSTED',
        'NO_OTHER_PROTOCOL_GLOBAL_BALANCE_CLAIM','COUNTERFACTUAL_PREDEPLOYMENT_CTF_TRANSFERS_NOT_ENUMERATED']


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def expected_wallet():
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    from polymarket._internal.wallet import derive_beacon_deposit_wallet_address
    return derive_beacon_deposit_wallet_address(EXPECTED,env.wallet_derivation)


def assess(snapshot,now_ms):
    missing=[];recovery=[]
    try:
        if snapshot['chain_id']!=137 or snapshot['wallet'].lower()!=expected_wallet().lower():raise ValueError()
        if type(snapshot['block_number']) is not int or snapshot['block_number']<0 or not re.fullmatch('0x[0-9a-fA-F]{64}',snapshot['block_hash']):raise ValueError()
        if not 0<=now_ms-snapshot['timestamp_ms']<=120000:missing.append('SNAPSHOT_STALE')
        if snapshot.get('block_hash_rechecked') is not True:missing.append('BLOCK_NOT_RECHECKED')
        if snapshot.get('dedicated_wallet_policy')!='D6_DEDICATED_FROM_GENESIS':missing.append('DEDICATED_WALLET_POLICY_MISSING')
        if snapshot.get('local_prior_state') not in ('NO_AUTHORITATIVE_LEDGER_CONFIGURED','VERIFIED_NO_ACTIVE_SESSION'):
            recovery.append('LOCAL_PRIOR_STATE_UNRESOLVED')
        c=snapshot['collateral']
        if c['contract']!=CONTRACT or not re.fullmatch('[0-9]+',c['balance_raw']) or not re.fullmatch('[0-9a-f]{64}',c['qualification_sha256']):raise ValueError()
        views=snapshot['views']
        for name in ('positions','orders','trades'):
            view=views[name]
            if view.get('pagination_complete') is not True or not isinstance(view.get('rows'),list):missing.append(name.upper()+'_READ_INCOMPLETE');continue
            if not 0<=now_ms-view['observed_ms']<=120000:missing.append(name.upper()+'_STALE')
            # First baseline cannot explain nonempty account activity automatically.
            if view['rows']:recovery.append(name.upper()+'_NONEMPTY_REQUIRES_EXPLANATION')
            if view.get('repeat_sha256')!=digest(view['rows']):recovery.append(name.upper()+'_CHANGED_DURING_SNAPSHOT')
        ctf=snapshot['conditional_assets']
        if ctf.get('contract')!=CTF or ctf.get('status')!='PASS_SCOPED_READS':missing.append('CTF_DISCOVERY_MISSING')
        if ctf.get('start_boundary')!='WALLET_CODE_ONSET_READ' or ctf.get('to_block')!=snapshot['block_number'] or ctf.get('block_hash')!=snapshot['block_hash']:missing.append('CTF_RANGE_NOT_ANCHORED')
        assets=ctf.get('balances')
        if not isinstance(assets,dict):missing.append('DISCOVERED_BALANCES_MISSING')
        else:
            for asset,raw in assets.items():
                if not re.fullmatch('[0-9]+',asset) or not 0<=int(asset)<2**256 or not re.fullmatch('[0-9]+',raw):raise ValueError()
                if int(raw)>0:recovery.append('CONDITIONAL_INVENTORY_NONZERO')
            if not set(snapshot.get('journal_assets',[]))<=set(assets):missing.append('JOURNAL_ASSET_NOT_CHECKED')
        if snapshot.get('coverage_limitations')!=LIMITS:missing.append('COVERAGE_LIMITS_NOT_RECORDED')
    except (KeyError,TypeError,ValueError,AttributeError):missing.append('SNAPSHOT_CONTRACT_INVALID')
    return {'phase':'RECOVERY_REQUIRED' if recovery else 'GENESIS_PENDING' if missing else 'GENESIS_RECONCILED',
            'accepted':not (missing or recovery),'reasons':sorted(set(recovery+missing)),
            'scope':'D6_FORWARD_LEDGER_SCOPED_BASELINE','prior_history_globally_known':False}


def create_genesis(path,snapshot,*,now_ms=None,before_publish=None):
    decision=assess(snapshot,int(time.time()*1000) if now_ms is None else now_ms)
    if not decision['accepted']:return {**decision,'created':False}
    path=Path(path)
    if path.exists():return {'phase':'GENESIS_REFUSED','created':False,'reasons':['LEDGER_ALREADY_EXISTS']}
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='genesis-',suffix='.tmp',dir=path.parent);os.close(fd)
    try:
        with closing(sqlite3.connect(temp)) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE genesis(id INTEGER PRIMARY KEY CHECK(id=1),snapshot TEXT NOT NULL,hash TEXT NOT NULL)')
            db.execute('CREATE TABLE d6_events(id INTEGER PRIMARY KEY,ts_ms INTEGER NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,previous_hash TEXT NOT NULL,hash TEXT NOT NULL)')
            db.execute('INSERT INTO genesis VALUES(1,?,?)',(canonical(snapshot),digest(snapshot)))
            db.commit()
        with open(temp,'r+b') as handle:os.fsync(handle.fileno())
        if before_publish:before_publish()
        # Atomic publication with no replacement; source and target on same filesystem.
        os.link(temp,path)
        return {**decision,'created':True,'snapshot_sha256':digest(snapshot)}
    finally:
        if os.path.exists(temp):os.unlink(temp)


def read_genesis(path):
    p=Path(path).resolve(strict=True)
    with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        row=db.execute('SELECT snapshot,hash FROM genesis WHERE id=1').fetchone()
        if not row:raise ValueError('GENESIS_MISSING')
        snapshot=json.loads(row[0]);last=row[1]
        if digest(snapshot)!=last or not assess(snapshot,snapshot['timestamp_ms'])['accepted']:raise ValueError('GENESIS_INVALID')
        recovery=False;event_count=0
        for event in db.execute('SELECT id,ts_ms,kind,payload,previous_hash,hash FROM d6_events ORDER BY id'):
            i,stamp,kind,payload,previous,h=event
            if i!=event_count+1 or previous!=last or digest({'id':i,'ts_ms':stamp,'kind':kind,'payload':json.loads(payload),'previous_hash':previous})!=h:raise ValueError('JOURNAL_INVALID')
            event_count=i;last=h;recovery|=kind=='RECOVERY_REQUIRED'
    return {'phase':'RECOVERY_REQUIRED' if recovery else 'GENESIS_RECONCILED','snapshot_sha256':row[1],
            'snapshot':snapshot,'last_hash':last,'event_count':event_count,'integrity_verified':True,
            'reconciled_now':False,'prior_history_globally_known':False}


def append_activity(path,kind,payload,*,now_ms=None):
    if kind not in {'INTENT','ACK','FILL','CANCEL_OBSERVATION','SETTLEMENT','RECOVERY_REQUIRED','RECONCILIATION'}:raise ValueError('EVENT_KIND')
    prior=read_genesis(path)
    if kind=='INTENT' and prior['phase']=='RECOVERY_REQUIRED':raise ValueError('RECOVERY_REQUIRED')
    stamp=int(time.time()*1000) if now_ms is None else now_ms
    with closing(sqlite3.connect(Path(path))) as db:
        db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT id,hash FROM d6_events ORDER BY id DESC LIMIT 1').fetchone()
        last=row[1] if row else prior['snapshot_sha256'];i=(row[0] if row else 0)+1
        if last!=prior['last_hash']:raise ValueError('CONCURRENT_JOURNAL_CHANGE')
        item={'id':i,'ts_ms':stamp,'kind':kind,'payload':payload,'previous_hash':last}
        db.execute('INSERT INTO d6_events VALUES(?,?,?,?,?,?)',(i,stamp,kind,canonical(payload),last,digest(item)))
        db.commit()
    return digest(item)


def reconcile_empty_baseline(path,remote):
    prior=read_genesis(path)
    # No numeric PnL or "flat" inference from a genesis label. Check new evidence.
    ok=prior['phase']=='GENESIS_RECONCILED' and prior['event_count']==0 and remote.get('scope_complete') is True and remote.get('fresh') is True
    ok=ok and remote.get('wallet','').lower()==prior['snapshot']['wallet'].lower()
    ok=ok and remote.get('collateral_balance_raw')==prior['snapshot']['collateral']['balance_raw']
    ok=ok and remote.get('open_orders')==[] and isinstance(remote.get('balances'),dict)
    ok=ok and set(prior['snapshot']['conditional_assets']['balances'])<=set(remote.get('balances',{}))
    ok=ok and all(str(v)=='0' for v in remote.get('balances',{}).values())
    if not ok:append_activity(path,'RECOVERY_REQUIRED',{'reason':'REMOTE_LOCAL_DIVERGENCE_OR_INCOMPLETE'})
    return bool(ok)
