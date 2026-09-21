"""Candidate acceleration, never imported by the historical controller."""
import ast,inspect,pathlib,sqlite3,textwrap,types,time
from contextlib import closing
import sys
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from app.d5 import replay as original_replay
from audit_next import audit as next_audit

# Only eliminate an unused context for the exact NoTrade class, never arbitrary strategies.
_tree=ast.parse(textwrap.dedent(inspect.getsource(original_replay.Replay.process)))
_replaced=0
for _node in ast.walk(_tree):
    if isinstance(_node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='context' for t in _node.targets):
        _node.value=ast.IfExp(test=ast.parse('type(self.strategy) is NoTrade',mode='eval').body,body=ast.Constant(None),orelse=_node.value)
        _replaced+=1
assert _replaced==1
# Preserve the original JSON finite-number/serializability check for BOOKs.
# Only the discarded JSON decode and causal feature/context allocation are skipped.
for _i,_stmt in enumerate(_tree.body[0].body):
    if isinstance(_stmt,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='context' for t in _stmt.targets):
        _guard=ast.parse("if type(self.strategy) is NoTrade:\n    if kind == 'BOOK': encode(payload)\n    if kind == 'BTC': self.btc.at(now)").body[0]
        _tree.body[0].body.insert(_i,_guard)
        break
_namespace=dict(vars(original_replay))
exec(compile(ast.fix_missing_locations(_tree),__file__,'exec'),_namespace)
class FastNoTradeReplay(original_replay.Replay):
    process=_namespace['process']
_globals=dict(original_replay.replay_database.__globals__)
_globals['Replay']=FastNoTradeReplay
replay_database=types.FunctionType(original_replay.replay_database.__code__,_globals,'replay_database',original_replay.replay_database.__defaults__)

TABLES=('schema_info','sessions','markets','events','book_sides','anchors','hedge_attempts')
REPLACEMENTS={('events','payload_json'):"CASE WHEN kind='REJECT' THEN payload_json ELSE '{}' END",('book_sides','bids_json'):"'[]'",('book_sides','asks_json'):"'[]'",('anchors','features_json'):"'{}'",('markets','metadata_json'):"'{}'"}
INDEXES=(('events','session_id,event_id'),('events','market_slug,event_id'),('events','event_id'),('markets','condition_id,market_slug'),('book_sides','event_id,side'),('anchors','event_id,first_side'),('anchors','anchor_id'),('anchors','session_id,anchor_condition_id,anchor_market_slug,status'))

def build_projection(source,destination,progress=None,batch_size=10000):
    """Disposable metadata cache, NOT a replacement dataset or integrity evidence.

    Original integrity/FK checks and both replays MUST use source, never destination.
    No triggers/constraints are installed on the cache, so anomalies remain visible.
    """
    source=pathlib.Path(source).resolve();destination=pathlib.Path(destination).resolve()
    if source==destination or destination.exists():raise FileExistsError('Projection must be a new, separate file')
    destination.touch(exist_ok=False)
    started=time.monotonic()
    def emit(**state):
        if progress:progress({'phase':'METADATA_PROJECTION','elapsed_seconds':time.monotonic()-started,**state})
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(destination)) as dst:
        src.execute('PRAGMA query_only=ON');src.execute('BEGIN')
        dst.execute('PRAGMA cache_size=-32768')
        def pulse():
            emit(step='sqlite_work')
            return 0
        src.set_progress_handler(pulse,100000)
        dst.set_progress_handler(pulse,100000)
        for table in TABLES:
            cols=src.execute(f'PRAGMA table_info({table})').fetchall()
            if not cols:raise ValueError('Missing required table '+table)
            if any(not c[1].replace('_','').isalnum() for c in cols):raise ValueError('Unexpected column name')
            definitions=','.join('"'+c[1]+'" '+(c[2] or 'BLOB') for c in cols)
            dst.execute(f'CREATE TABLE {table} ({definitions})')
            total=src.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
            expressions=','.join(REPLACEMENTS.get((table,c[1]),'"'+c[1]+'"') for c in cols)
            cursor=src.execute(f'SELECT {expressions} FROM {table}')
            done=0;emit(table=table,rows=done,total=total)
            while batch:=cursor.fetchmany(batch_size):
                dst.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in cols)})',batch)
                done+=len(batch);emit(table=table,rows=done,total=total)
            dst.commit()
        for i,(table,columns) in enumerate(INDEXES):
            emit(table=table,step='index',index=i)
            dst.execute(f'CREATE INDEX cache_index_{i} ON {table}({columns})')
        dst.commit()
    emit(step='complete',bytes=destination.stat().st_size)

def compact_audit(source,session,projection,progress=None):
    build_projection(source,projection,progress)
    return next_audit(projection,session,progress)
