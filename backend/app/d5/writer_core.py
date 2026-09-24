"""Ordered SHADOW writer core; experimental, not selected by live.py.

The owner must be the sole SQLite writer. Receipt times remain raw; processing
availability uses this owner's clock, never the producer's captured timestamp.
"""
from pathlib import Path
import time
from .store import Store
from .observer import Observer
from .features import BTCFeatures


class WriterCore:
    def __init__(self, path, *, clock=None, config=None):
        if Path(path).exists():
            raise FileExistsError('Writer requires a new database')
        self.clock = clock or (lambda: time.time_ns() // 1_000_000)
        store_config = {'mode':'SHADOW','strategy':'NO_TRADE','capital':500,
                        'timestamp_contract':'D5.1','writer':'process-writer'}
        store_config.update(config or {})
        self.store = Store(path, store_config, compress_payloads=True)
        self.observer = Observer(self.store)
        self.btc = BTCFeatures()
        self.last_generation = {}
        self.next_sequence = 0
        self.processed_sequence = -1
        self.committed_sequence = -1
        self.closed = False
        self.failed = False
        self.dirty_sequence = -1

    def apply(self, command):
        try:
            return self._apply(command)
        except Exception as exc:
            self.fail(exc)
            raise

    def _apply(self, command):
        if self.closed or self.failed:
            raise RuntimeError('WRITER_NOT_ACCEPTING_COMMANDS')
        sequence = command['sequence']
        if type(sequence) is not int or sequence != self.next_sequence:
            raise ValueError('WRITER_SEQUENCE_MISMATCH')
        kind = command['kind']
        received = command['received_ts_ms']
        if type(received) is not int:
            raise ValueError('INVALID_COMMAND_RECEIPT')
        processed_at = max(self.clock(), received, self.store.last_available)
        identity = command.get('identity')
        generation = command.get('generation')
        event_id = None
        if kind == 'ACTIVATE':
            # A delayed reconnect/discovery may try to reactivate a market already
            # fenced as retired. This is a data-quality reject, not a terminal
            # writer failure: preserve evidence and keep the writer alive.
            if identity.key in self.observer.retired:
                event_id, _ = self.store.event('REJECT',
                    {'reason':'CROSS_MARKET_REJECT','detail':'retired identity','command_kind':'ACTIVATE'},
                    received_ts_ms=received,identity=identity,generation=generation,
                    available_ts_ms=processed_at)
            else:
                self.observer.activate(identity, generation, processed_at, command.get('metadata'))
                self.last_generation[identity.key] = generation
        elif kind == 'BOOK':
            snapshot = command['snapshot']
            if snapshot['received_ts_ms'] != received:
                raise ValueError('RECEIPT_TIMESTAMP_MISMATCH')
            event_id = self.observer.observe(identity, generation, snapshot,
                                             lambda: self.btc.at(processed_at), processed_at)
        elif kind == 'BTC':
            tick = command['tick']
            if tick['recv_ts_ms'] != received:
                raise ValueError('RECEIPT_TIMESTAMP_MISMATCH')
            event_id, available = self.store.event('BTC',tick,received_ts_ms=received,
                event_ts_ms=tick.get('event_ts_ms'),available_ts_ms=processed_at)
            self.btc.update(available,tick)
        elif kind == 'REJECT':
            payload = command['payload']
            event_id, _ = self.store.event('REJECT',payload,received_ts_ms=received,
                event_ts_ms=command.get('event_ts_ms'),identity=identity,generation=generation,
                available_ts_ms=processed_at)
        elif kind == 'EVENT':
            event_kind = command['event_kind']
            if event_kind not in ('CLOCK_SAMPLE','DISCOVERY_EMPTY','DISCOVERY_ERROR',
                                  'ROTATION','WS_ERROR','RECONNECT','BTC_CONNECTED','BTC_DISCONNECTED','BTC_ERROR','BTC_RECONNECT','COLLECTION_STOP'):
                raise ValueError('UNSUPPORTED_WRITER_EVENT')
            event_id, _ = self.store.event(event_kind,command['payload'],received_ts_ms=received,
                identity=identity,generation=generation,available_ts_ms=processed_at)
        elif kind == 'INVALIDATE':
            active = self.observer.active.get(identity.market_duration)
            if active == (identity,generation):
                self.observer.active.pop(identity.market_duration)
                self.observer.invalidate(identity, processed_at, command['reason'])
            elif identity.key in self.observer.retired and self.last_generation.get(identity.key)==generation:
                pass  # An earlier ordered EXPIRE already closed this exact generation.
            else:
                raise ValueError('INVALIDATE_GENERATION_MISMATCH')
        elif kind == 'EXPIRE':
            self.observer.expire(processed_at)
        elif kind == 'FLUSH':
            self.store.flush()
        elif kind == 'STOP':
            status = command.get('status','STOPPED')
            if status not in ('STOPPED','STOPPED_BY_USER_CLEAN','FAILED'):
                raise ValueError('INVALID_STOP_STATUS')
            cleanup_errors = command.get('cleanup_errors',[])
            if cleanup_errors:status='FAILED'
            if not command.get('collection_stop_already_recorded'):
                self.store.event('COLLECTION_STOP',{**command.get('payload',{}),'last_input_sequence':sequence,
                    'ingress_stop_ts_ms':received},received_ts_ms=received,available_ts_ms=processed_at)
            for active_identity, _ in list(self.observer.active.values()):
                self.observer.invalidate(active_identity,processed_at,'SESSION_END')
            self.observer.active.clear()
            self.store.event('SESSION_END',{**command.get('payload',{}),'cleanup_errors':cleanup_errors,
                             'last_input_sequence':sequence},received_ts_ms=received,available_ts_ms=processed_at)
            self.store.close(status)
            self.closed = True
        else:
            raise ValueError('UNSUPPORTED_WRITER_COMMAND')
        self.processed_sequence = sequence
        self.next_sequence += 1
        if kind in ('FLUSH','STOP'):
            self.committed_sequence = sequence
        else:
            self.dirty_sequence = sequence
        return {'sequence':sequence,'event_id':event_id,'processed_at_ms':processed_at,
                'committed_sequence':self.committed_sequence,'closed':self.closed,
                'counts':dict(self.store.counts)}

    def fail(self, error):
        """Owner failure is terminal. Already written evidence is retained as FAILED."""
        if self.closed:
            return
        self.failed = True
        try:
            now = max(self.clock(),self.store.last_available)
            self.store.event('WRITER_FAILURE', {'error':str(error),
                             'processed_sequence':self.processed_sequence,
                             'committed_sequence':self.committed_sequence},
                             received_ts_ms=now,available_ts_ms=now)
            self.store.close('FAILED')
        finally:
            self.store.db.close()
            self.closed = True
