"""Structured terminal/file logging reusing the offline rotation implementation.
No stdout/stderr interception (which could accidentally capture credentials).
"""
import shutil,re
from pathlib import Path
from .core import Journal,encoded
from .offline import RotatingLog,sanitize,SAFE_EVENTS,SENSITIVE,durable

# 5-hour rotation for real calibration artifacts (18 000 seconds).
# The raw JSONL journal (LoggedJournal) persists independently across rotations
# so crash-at-4h59m never loses 5h of data.
REAL_CALIBRATION_ROTATION_SECONDS = 18000

EVENTS=SAFE_EVENTS|{'ARM_STATE','ENTRY_DUE','SEND_DISPATCH_INTENT','POST_ORDER_BOOK',
 'CALIBRATION_EXCEPTION','RECOVERY_COMPLETE','RECOVERY_WAIT','BACKGROUND_TASK_ENDED',
 'EXPOSURE_CUSTODY_HANDOFF','ACCOUNT_OBSERVATION_DURING_ORDER','OPPORTUNITY_SKIPPED','OPPORTUNITY_COMPLETE',
 'ACCOUNT_MONITOR_FAILURE','WS_RECONNECTING','WS_RECONNECTED','WS_RECONNECT_FAILURE'}
PAYLOAD_FIELDS={
 'CALIBRATION_EXCEPTION':{'incident_id','exception_type','classification','message_redacted','exposure_management'},
 'RECOVERY_COMPLETE':{'cleared_transient_errors','remaining_v1_errors'},
 'RECOVERY_WAIT':{'reasons','stop_new_entries','waiting_for_reconciliation','qualified'},
 'BACKGROUND_TASK_ENDED':{'incident_id','task_name','exception_type','message_redacted','transient','restart_attempted'},
 'INIT':{'account','starting_cash','version','max_entry','max_total','max_entries'},
 'ARM_STATE':{'armed','pid','nonce','persisted_arming'},
 'STOP':{'reason','details'},
 'RECONCILIATION_OBSERVATION':{'snapshot','decision_ms'},
 'RECONCILED':{'CALIBRATION_ACCOUNT_RECONCILED','decision_ms','D6_current_inventory_proven'},
 'SHADOW_SEALED':{'opportunity_id','sha256','shadow'},
 'RESERVE':{'opportunity_id','notional','fee_ceiling','trade_number','fee_risk'},
 'DURABLE_INTENT':{'client_id','opportunity_id','trade_number','side','token','market','price','shares','notional','book','order_type','send_intent_ms','send_proven'},
 'ACK_RESPONSE':{'client_id','response','receive_ms','local_send_call_ms'},
 'FILL_OBSERVATION':{'client_id','fill'},
 'ORDER_TERMINAL_OBSERVATION':{'client_id','status','cumulative_shares'},
 'SEND_DISPATCH_INTENT':{'client_id','local_send_call_ms','socket_send_proven'},
 'POST_ORDER_BOOK':{'client_id','book'},
 'CHECKPOINT':{'report','journal_previous','journal_sequence','arm_persisted'},
 'EXPOSURE_CUSTODY_HANDOFF':{'account','experiment_id','exposure','exposure_revision','exposure_digest','journal_sequence','owner','receipt_id','accepted_ms','future_result_client_ids'},
 'ACCOUNT_OBSERVATION_DURING_ORDER':{'snapshot','decision_ms'},
 'OPPORTUNITY_SKIPPED':{'signal_receive_ts','reason'},
 'OPPORTUNITY_COMPLETE':{'opportunity_id'},
 'ENTRY_DUE':{'opportunity_id','entry_due_ms','signal_receive_ts','signal_decision_ts','signal_source_ts','direction','btc_move','btc_lookback_evidence'},
 'WS_RECONNECTING':{'generation','attempt'},
 'WS_RECONNECTED':{'generation','rest_seeded_tokens','state'},
 'WS_RECONNECT_FAILURE':{'exception_type','generation','attempt'},
 'ACCOUNT_MONITOR_FAILURE':{'exception_type','message','component','failures'},
}
class LiveLog(RotatingLog):
    def __init__(self,*args,max_bytes=64*1024**2,on_fault=None,require_drive=None,**kwargs):
        self.public_tokens=set();self.public_markets=set();self.public_transactions=set()
        self.total_bytes=0;self.max_bytes=max_bytes;self.on_fault=on_fault or (lambda reason:None)
        directory=Path(args[0])
        if require_drive and directory.resolve().drive.lower()!=require_drive.lower():raise ValueError('LOG_TARGET_DRIVE')
        if directory.exists() and (not directory.is_dir() or directory.is_symlink()):raise ValueError('LOG_TARGET_INVALID')
        directory.mkdir(parents=True,exist_ok=True)
        self.directory_lock=(directory/'.writer.lock').open('a+b')
        try:
            import msvcrt
            self.directory_lock.seek(0);msvcrt.locking(self.directory_lock.fileno(),msvcrt.LK_NBLCK,1)
            super().__init__(*args,**kwargs)
        except BaseException:self.directory_lock.close();raise
    def close(self):
        try:super().close()
        finally:self.directory_lock.close()
    def fault(self,reason):
        self.failed=True
        try:self.on_fault(reason)
        except Exception:pass
    def tick(self):
        try:
            if shutil.disk_usage(self.directory).free<512*1024**2:raise OSError('LOG_DISK_LOW')
            if sum(p.stat().st_size for p in self.directory.glob('*.log'))>self.max_bytes:raise OSError('LOG_AGGREGATE_QUOTA')
            ROTATION = REAL_CALIBRATION_ROTATION_SECONDS
            with self.lock:
                if self.closed: return
                if self.failed: raise OSError('LOG_FAILED')
                if self.clock()-self.started >= ROTATION:
                    import copy
                    if self.snapshot is not None:
                        stamp = self.utc().strftime('%Y%m%d_%H%M%S')
                        name = f'REAL_CALIBRATION_{self.session}_p{self.part:04d}_{stamp}_5H.json'
                        durable(self.directory / name, copy.deepcopy(self.snapshot()))
                    self.file.close(); self.part += 1; self.started = self.clock(); self._open()
        except BaseException:
            self.fault('LOG_ROTATION_OR_STORAGE_FAILURE');raise
    def canonical_tree(self,value,key=None):
        # Typed public IDs are explicitly registered; untyped hex remains secret-like.
        if key=='token':return value if type(value) is str and value in self.public_tokens else '[REDACTED]'
        if key in ('market','condition_id') and type(value) is str and value in self.public_markets:return value
        if key=='transaction_hash' and type(value) is str and value in self.public_transactions and re.fullmatch(r'0x[0-9a-fA-F]{64}',value):return value
        if key=='transactionsHashes' and isinstance(value,(list,tuple)):
            return [self.canonical_tree(v,'transaction_hash') for v in value]
        if isinstance(value,dict):
            return {k:('[REDACTED]' if any(s in re.sub('[^a-z]','',str(k).lower()) for s in (*SENSITIVE,'password','accesstoken','refreshtoken')) else self.canonical_tree(v,k)) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [self.canonical_tree(v,key) for v in value]
        return sanitize(value)
    def encode_record(self,row):return encoded(row)  # already canonical; never re-sanitize a sealed record
    def write(self,row):
        with self.lock:
            from .log_schema import nested_payload
            row=dict(row)
            sealed_shadow=row.get('payload',{}).get('shadow') if row.get('kind')=='SHADOW_SEALED' else None
            if 'payload' in row:
                fields=PAYLOAD_FIELDS.get(row.get('kind'),set())
                row['payload']=nested_payload(row.get('kind'),{k:v for k,v in row['payload'].items() if k in fields},self.public_tokens) if isinstance(row['payload'],dict) else {}
            allowed={'experiment_id','hash','kind','payload','previous','seq','mode'}
            data={**self.canonical_tree({k:v for k,v in row.items() if k in allowed}),'mode':'REAL_CALIBRATION_PREPARATION'}
            if row.get('kind')=='SHADOW_SEALED':
                from .core import digest
                p=data['payload']
                if p.get('shadow')!=sealed_shadow or digest(p['shadow'])!=p.get('sha256'):
                    self.fault('NONCANONICAL_SHADOW_LOG');raise ValueError('NONCANONICAL_SHADOW_LOG')
            size=len((encoded(data)+'\n').encode())
            if sum(p.stat().st_size for p in self.directory.glob('*.log'))+size>self.max_bytes or shutil.disk_usage(self.directory).free<512*1024**2:
                self.fault('LOG_STORAGE_LIMIT');raise OSError('LOG_STORAGE_LIMIT')
            try:super().write(data);self.total_bytes+=size
            except BaseException:self.fault('LOG_WRITE_OR_CONSOLE_FAILURE');raise

class LoggedJournal(Journal):
    def __init__(self,path,experiment_id,log,**quota):
        self.log=log;super().__init__(path,experiment_id,**quota)
    def project_shadow(self,shadow):
        from .log_schema import project,SHADOW
        return self.log.canonical_tree(project(shadow,SHADOW,self.log.public_tokens))
    def append(self,kind,payload):
        with self.lock:return self._logged_append(kind,payload)
    def _logged_append(self,kind,payload):
        if kind not in EVENTS:raise ValueError('UNREVIEWED_LOG_EVENT')
        try:
            def scrub(x):
                if isinstance(x,dict):return {k:('[REDACTED]' if re.sub('[^a-z]','',str(k).lower()) in ('password','accesstoken','refreshtoken') else scrub(v)) for k,v in x.items()}
                if isinstance(x,(list,tuple)):return [scrub(v) for v in x]
                return x
            if kind not in PAYLOAD_FIELDS:raise ValueError('LIVE_PAYLOAD_SCHEMA_REQUIRED')
            clean=scrub({k:v for k,v in payload.items() if k in PAYLOAD_FIELDS[kind]})
            if kind=='STOP' and isinstance(clean.get('details'),dict):
                clean['details']={k:v for k,v in clean['details'].items() if k in ('incident_id','exception_type','exposure_management','local_send_call_ms','socket_send_proven')}
            if kind=='ACK_RESPONSE':
                clean={k:v for k,v in clean.items() if k in ('client_id','response','receive_ms','local_send_call_ms')}
                response=clean.get('response',{})
                if isinstance(response,dict):
                    allowed={'ok','order_id','status','error_code','exchange_raw'}
                    response={k:v for k,v in response.items() if k in allowed}
                    raw=response.get('exchange_raw')
                    if isinstance(raw,dict):response['exchange_raw']={k:v for k,v in raw.items() if k in ('status','orderID','success','transactionsHashes','tradeIDs','makingAmount','takingAmount')}
                    clean['response']=response
            from .log_schema import nested_payload
            clean=nested_payload(kind,clean,self.log.public_tokens)
            clean=self.log.canonical_tree(clean)
            if kind=='SHADOW_SEALED':
                from .core import digest
                if clean.get('shadow')!=payload.get('shadow') or digest(clean['shadow'])!=clean.get('sha256'):raise ValueError('NONCANONICAL_SHADOW')
            if kind=='STOP':clean={k:v for k,v in clean.items() if k in ('reason','details')}
            row=super().append(kind,clean)
            self.log.write(row);return row
        except BaseException:
            self.failed=True;raise
