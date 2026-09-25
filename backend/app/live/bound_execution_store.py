"""Separate durable execution journal bound to an immutable Genesis.

No production file is created on import. Hashes detect inconsistent local edits,
not malicious rewriting of the entire DB. This journal does not prove remote
completeness, settlement fees or PnL and cannot authorize a submission.
"""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from decimal import Decimal
from .execution import ExecutionStore, ExecutionBlocked
from .genesis_ledger import read_genesis, canonical, digest


class BoundExecutionStore(ExecutionStore):
    def __init__(self, path, *, genesis_path, expected_genesis_hash, create=False):
        self.path = Path(path).resolve()
        self.genesis_path = Path(genesis_path).resolve(strict=True)
        if self.path == self.genesis_path:
            raise ExecutionBlocked('SESSION_MUST_NOT_OVERWRITE_GENESIS')
        prior = read_genesis(self.genesis_path)
        if (prior['snapshot_sha256'] != expected_genesis_hash
                or prior['phase'] != 'GENESIS_RECONCILED' or prior['event_count'] != 0):
            raise ExecutionBlocked('SESSION_GENESIS_BINDING_REJECTED')
        self.binding = dict(schema=1, genesis_hash=expected_genesis_hash,
                            genesis_journal_hash=prior['last_hash'])
        self.root_hash = digest(self.binding)
        if create:
            self._create()
        self.db = sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        try:
            row = self.db.execute('SELECT value FROM session_binding WHERE id=1').fetchone()
            if row is None or json.loads(row[0]) != self.binding:
                raise ExecutionBlocked('SESSION_BINDING_MISMATCH')
            self.load()
        except Exception:
            self.db.close()
            raise ExecutionBlocked('SESSION_INTEGRITY_REQUIRED') from None

    def _create(self):
        if self.path.exists():
            raise FileExistsError('SESSION_ALREADY_EXISTS')
        fd, temp = tempfile.mkstemp(prefix='d6-session-',suffix='.tmp',dir=self.path.parent)
        os.close(fd)
        try:
            db = sqlite3.connect(temp)
            try:
                db.execute('PRAGMA synchronous=FULL')
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE session_binding(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
                db.execute('CREATE TABLE execution_state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
                db.execute('CREATE TABLE execution_events(id INTEGER PRIMARY KEY,ts_ms INTEGER NOT NULL,event TEXT NOT NULL,value TEXT NOT NULL)')
                db.execute('CREATE TABLE execution_chain(id INTEGER PRIMARY KEY,previous_hash TEXT NOT NULL,hash TEXT NOT NULL)')
                db.execute('INSERT INTO session_binding VALUES(1,?)',(canonical(self.binding),))
                db.commit()
            finally:
                db.close()
            with open(temp,'r+b') as handle:
                os.fsync(handle.fileno())
            os.link(temp,self.path)  # Atomic publication; never replaces an existing file.
        finally:
            os.unlink(temp)

    @staticmethod
    def _item(row, previous):
        i,stamp,event,payload = row
        return dict(id=i,ts_ms=stamp,event=event,state=json.loads(payload),previous_hash=previous)

    def _check_binding(self):
        row = self.db.execute('SELECT value FROM session_binding WHERE id=1').fetchone()
        if row is None or json.loads(row[0]) != self.binding:
            raise ExecutionBlocked('SESSION_BINDING_MISMATCH')
        prior = read_genesis(self.genesis_path)
        if (prior['snapshot_sha256'] != self.binding['genesis_hash']
                or prior['last_hash'] != self.binding['genesis_journal_hash']
                or prior['phase'] != 'GENESIS_RECONCILED'):
            raise ExecutionBlocked('GENESIS_CHANGED_RECOVERY_REQUIRED')

    def load(self):
        self._check_binding()
        own_transaction = not self.db.in_transaction
        if own_transaction:
            self.db.execute('BEGIN')
        try:
            previous = self.root_hash
            last_state = None
            count = 0
            for row in self.db.execute('SELECT id,ts_ms,event,value FROM execution_events ORDER BY id'):
                count += 1
                chain = self.db.execute('SELECT previous_hash,hash FROM execution_chain WHERE id=?',(row[0],)).fetchone()
                if row[0] != count or chain != (previous,digest(self._item(row,previous))):
                    raise ExecutionBlocked('SESSION_CHAIN_INVALID')
                previous = chain[1]
                last_state = json.loads(row[3])
            if self.db.execute('SELECT count(*) FROM execution_chain').fetchone()[0] != count:
                raise ExecutionBlocked('SESSION_CHAIN_INVALID')
            state = super().load()
            if state != last_state:
                raise ExecutionBlocked('SESSION_STATE_NOT_JOURNALED')
            return state
        finally:
            if own_transaction:
                self.db.execute('ROLLBACK')  # End read snapshot, never mutate persisted data.

    def _after_event_write(self):
        row = self.db.execute('SELECT id,ts_ms,event,value FROM execution_events ORDER BY id DESC LIMIT 1').fetchone()
        prior = self.db.execute('SELECT hash FROM execution_chain ORDER BY id DESC LIMIT 1').fetchone()
        previous = prior[0] if prior else self.root_hash
        self.db.execute('INSERT INTO execution_chain VALUES(?,?,?)',
                        (row[0],previous,digest(self._item(row,previous))))

    def record_cash_observation(self, evidence, *, expected_transactions, now_ms):
        """Journal a bounded cash comparison, not a fee or current-inventory proof."""
        from copy import deepcopy
        from .cash_evidence import reconcile_cash_delta
        prior_state = self.load()
        if not prior_state or prior_state.get('phase') != 'CLOSED':
            raise ExecutionBlocked('CASH_OBSERVATION_REQUIRES_CLOSED_CYCLE')
        genesis = read_genesis(self.genesis_path)['snapshot']
        before = evidence.get('before',{})
        if (before.get('block_number') != genesis['block_number']
                or before.get('block_hash') != genesis['block_hash']
                or before.get('balance_raw') != genesis['collateral']['balance_raw']):
            raise ExecutionBlocked('CASH_BASELINE_MISMATCH')
        result = reconcile_cash_delta(evidence,expected_wallet=genesis['wallet'],
            expected_contract=genesis['collateral']['contract'],
            expected_transactions=expected_transactions,now_ms=now_ms)
        if result['status'] != 'CASH_DELTA_MATCHED':
            raise ExecutionBlocked('CASH_EVIDENCE_INVALID')
        # Retain only the public proof schema, never arbitrary caller metadata.
        clean = {k:deepcopy(evidence[k]) for k in ('chain_id','wallet','collateral_contract','canonical_observed_ms')}
        clean['before'] = {k:before[k] for k in ('block_number','block_hash','balance_raw')}
        clean['after'] = {k:evidence['after'][k] for k in ('block_number','block_hash','balance_raw','observed_ms')}
        blocks = {str(before['block_number']),str(evidence['after']['block_number'])}
        clean['receipts'] = []
        for wrapper in evidence['receipts']:
            r = wrapper['receipt']
            blocks.add(str(int(r['blockNumber'],16)))
            receipt = {k:r[k] for k in ('status','transactionHash','blockNumber','blockHash')}
            receipt['logs'] = [{k:deepcopy(log[k]) for k in
                ('address','topics','data','transactionHash','blockNumber','blockHash','logIndex','removed') if k in log}
                for log in r['logs']]
            clean['receipts'].append(dict(observed_ms=wrapper['observed_ms'],receipt=receipt))
        clean['canonical_blocks'] = {k:evidence['canonical_blocks'][k] for k in blocks}
        state = deepcopy(prior_state)
        state['cash_observation'] = dict(result=result,evidence=clean,expected_transactions=list(expected_transactions))
        self.write('CASH_DELTA_OBSERVATION',state,expected_state=prior_state)
        return result

    def projection(self):
        state = self.load()
        quantity = None
        if state is not None and 'bought' in state and 'sold' in state:
            bought,sold = Decimal(str(state['bought'])),Decimal(str(state['sold']))
            if not bought.is_finite() or not sold.is_finite() or not 0 <= sold <= bought:
                raise ExecutionBlocked('SESSION_QUANTITY_INVALID')
            quantity = str(bought-sold)
        return dict(cash_delta_status=(state or {}).get('cash_observation',{}).get('result',{}).get('status'),
                    phase=state['phase'] if state else 'NO_EXECUTION_RECORDED',
                    open_shares=quantity,quantity_basis='LAST_REPORTED_FILLS_NOT_CURRENT_REMOTE_INVENTORY',
                    genesis_hash=self.binding['genesis_hash'],cash_reconciled=False,
                    pnl=None,fees=None,current_inventory_proven=False,submit_allowed=False)

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
