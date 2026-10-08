"""Multi-token ledger that allows concurrent positions on different tokens.
Overrides the single-position ONE_POSITION_GATE to only block
same-token concurrent positions. Tracks multiple active opportunities.
"""
from decimal import Decimal
from .core import CalibrationLedger, dec, digest, redact, ZERO
import copy


class MultiCalibrationLedger(CalibrationLedger):
    """Multi-token ledger that allows concurrent positions on different tokens."""

    def __init__(self, journal, account, starting_cash):
        super().__init__(journal, account, starting_cash)
        self.active = set()
        # At startup, no positions/trades = reconciled by default.
        # Otherwise first signal before the reconcile cycle is blocked.
        self.reconciled = True

    def reserve(self, opportunity, notional, fee_ceiling, fee_risk=None, token=None):
        n, f = dec(notional), dec(fee_ceiling)
        if self.stop or self.stop_new_entries or self.recovery_only or not self.reconciled:
            raise ValueError('ENTRIES_STOPPED_OR_UNRECONCILED')
        if opportunity in self.trades:
            raise ValueError('DUPLICATE_OPPORTUNITY')
        if token and self.positions.get(token, ZERO) > 0:
            raise ValueError('ONE_POSITION_GATE')
        if not ZERO < n <= 25:
            raise ValueError('ENTRY_CAP_25')
        if self.allocated + n + f > 100 or n + f > self.cash:
            raise ValueError('EXPERIMENT_CAP_100')
        self.emit('RESERVE', {'opportunity_id': opportunity, 'notional': str(n),
                              'fee_ceiling': str(f), 'trade_number': self.attempts + 1,
                              'fee_risk': __import__('dataclasses').asdict(fee_risk) if fee_risk else None})
        self.trades[opportunity] = {'notional': n, 'fee_ceiling': f, 'spent': ZERO,
                                     'proceeds': ZERO, 'cash_fees': ZERO, 'share_fees': ZERO,
                                     'reserved': n + f, 'entry_terminal': False,
                                     'exit_terminal': False, 'orders': [], 'token': token}
        self.trades[opportunity]['fee_risk'] = fee_risk
        self.allocated += n + f
        self.active.add(opportunity)
        self.attempts += 1
        self.reconciled = False

    def intent(self, client_id, side, token, market, price, shares, notional, book, send_intent_ms):
        p, q, n = dec(price), dec(shares), dec(notional)
        if client_id in self.orders:
            raise ValueError('DUPLICATE_OR_UNRESERVED_ORDER')
        matching = [op for op in self.active if op in self.trades and self.trades[op].get('token') == token]
        if not matching:
            raise ValueError('DUPLICATE_OR_UNRESERVED_ORDER')
        op = matching[0]
        trade = self.trades[op]
        shadow_hash, shadow = self.shadows.get(op, (None, None))
        if shadow is None or digest(shadow) != shadow_hash:
            raise ValueError('SHADOW_IDENTITY_OR_HASH_MISMATCH')
        # Token/market are redacted in projected shadow, use trade record instead
        if trade.get('token') != token:
            raise ValueError('SHADOW_IDENTITY_OR_HASH_MISMATCH')
        if side not in ('BUY', 'SELL') or not ZERO < p < 1 or q <= 0 or not token or not market:
            raise ValueError('ORDER_INVALID')
        if any(o['side'] == side and o['opportunity_id'] == op for o in self.orders.values()):
            raise ValueError('NO_AUTOMATIC_RETRY')
        if side == 'BUY' and (self.stop or n > 25 or n > trade['notional'] or p * q > 25):
            raise ValueError('FORMATTED_ENTRY_CAP')
        if side == 'SELL' and (not self.reconciled or not trade['entry_terminal'] or q > self.positions.get(token, ZERO)):
            raise ValueError('EXIT_QUANTITY_UNPROVEN')
        risk = trade.get('fee_risk')
        if side == 'SELL' and risk and q + max(ZERO, dec(risk.outcome_shares) - trade['share_fees']) > self.positions.get(token, ZERO):
            raise ValueError('EXIT_SHARE_FEE_RESERVE')
        row = {'client_id': client_id, 'opportunity_id': op, 'trade_number': self.attempts,
               'side': side, 'token': token, 'market': market, 'price': str(p), 'shares': str(q),
               'notional': str(n), 'book': copy.deepcopy(book), 'order_type': 'FAK',
               'send_intent_ms': send_intent_ms, 'send_proven': False}
        self.emit('DURABLE_INTENT', row)
        self.orders[client_id] = {**row, 'order_id': None, 'terminal': False,
                                   'filled_shares': ZERO, 'filled_notional': ZERO,
                                   'reported_filled': None}
        trade['orders'].append(client_id)
        self.reconciled = False

    def reconcile(self, snapshot, now_ms):
        self.emit('RECONCILIATION_OBSERVATION', {'snapshot': redact(snapshot), 'decision_ms': now_ms})
        try:
            proofs = ('inventory_proven', 'cash_proven', 'orders_complete', 'trades_complete', 'positions_complete')
            if snapshot['account'] != self.account:
                raise ValueError('ACCOUNT_MISMATCH')
            if any(snapshot.get(x) is not True for x in proofs):
                raise ValueError('ACCOUNT_SCOPE_UNPROVEN')
            if snapshot['observed_ms'] < self.last_fill_receive_ms or not 0 <= now_ms - snapshot['observed_ms'] <= 5000:
                raise ValueError('ACCOUNT_STALE_OR_FUTURE')
            if snapshot.get('open_orders'):
                raise ValueError('UNKNOWN_OPEN_ORDER')
            if dec(snapshot['cash']) != self.cash:
                raise ValueError('BALANCE_MISMATCH')
            pos = {k: dec(v) for k, v in snapshot['positions'].items() if dec(v) != 0}
            if pos != {k: v for k, v in self.positions.items() if v != ZERO}:
                raise ValueError('POSITION_MISMATCH')
            if set(snapshot['trade_ids']) != set(self.fills):
                raise ValueError('TRADE_HISTORY_MISMATCH')
            known = {o['order_id'] for o in self.orders.values() if o['order_id']}
            if set(snapshot['terminal_order_ids']) != known or any(not o['terminal'] or o['reported_filled'] != o['filled_shares'] for o in self.orders.values()):
                raise ValueError('ORDER_STATE_UNKNOWN')
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            self.halt(str(exc))
            return False
        self.last_account_snapshot = copy.deepcopy(snapshot)
        self.reconciled = True
        self.emit('RECONCILED', {'CALIBRATION_ACCOUNT_RECONCILED': True, 'decision_ms': now_ms,
                                  'D6_current_inventory_proven': False})
        completed = [op for op in list(self.active) if op in self.trades]
        for op in completed:
            t = self.trades[op]
            tok = t.get('token')
            if t['entry_terminal'] and (t['spent'] == ZERO or t['exit_terminal']) and not self.positions.get(tok, ZERO) > ZERO:
                t['reserved'] = ZERO
                self.active.discard(op)
        return True

    def report(self):
        flat = not any(self.positions.values())
        known = self.reconciled
        return {'version': 'REAL_EXECUTION_CALIBRATION_V1', 'starting_experiment_budget': '100',
                'maximum_allowed_budget': '100',
                'starting_account_cash': str(self.starting_cash),
                'total_committed_notional': str(sum((x['notional'] for x in self.trades.values()), ZERO)),
                'lifetime_allocated_including_fee_ceiling': str(self.allocated),
                'reserved_amount': str(sum((x['reserved'] for x in self.trades.values()), ZERO)),
                'realized_spent_notional': str(self.spent),
                'realized_proceeds': str(self.proceeds),
                'actual_fees': {'collateral_cash': str(self.cash_fees), 'outcome_shares': str(self.share_fees)},
                'remaining_experiment_budget': str(Decimal(100) - self.allocated),
                'open_exposure': {k: str(v) for k, v in self.positions.items() if v},
                'open_exposure_at_risk_upper_bound': str(self.allocated) if not flat or self.active else '0',
                'exposure_known': known,
                'net_realized_pnl': str(self.cash - self.starting_cash) if flat and known else None,
                'gross_realized_pnl': str(self.proceeds - self.spent) if flat and known and self.share_fees == 0 else None,
                'entries_attempted': self.attempts, 'orders_attempted': len(self.orders),
                'orders_accepted': sum(o['order_id'] is not None for o in self.orders.values()),
                'fills': len(self.fills),
                'partial_fills': sum(o['terminal'] and ZERO < o['filled_shares'] < dec(o['shares']) for o in self.orders.values()),
                'no_fills': sum(o['terminal'] and o['filled_shares'] == ZERO for o in self.orders.values()),
                'CALIBRATION_ACCOUNT_RECONCILED': self.reconciled,
                'STOP_NEW_ENTRIES': self.stop or self.stop_new_entries, 'reasons': self.reasons.copy(),
                'SYSTEM_READY': False, 'current_inventory_proven': False, 'submit_allowed': False}

    def discard_opportunity(self, op):
        """Clean up a failed opportunity, releasing its capital.
        Called when SDK signing/submission fails, so the next opportunity can proceed.
        """
        if op in self.trades:
            t = self.trades[op]
            released = t.get('reserved', ZERO)
            self.allocated = max(ZERO, self.allocated - released)
            self.cash = self.cash  # unchanged, nothing was spent
            del self.trades[op]
            for cid in list(self.orders.keys()):
                if self.orders[cid].get('opportunity_id') == op:
                    del self.orders[cid]
        self.active.discard(op)
        # Decrement attempts so failed reserves don't permanently block new entries
        self.attempts = max(0, self.attempts - 1)
        self.reconciled = True
        self.emit('MULTI_DISCARD', {'opportunity_id': op})

    def custody_snapshot(self):
        exposure = {'account': self.account, 'active': list(self.active),
                    'positions': {k: str(v) for k, v in self.positions.items()},
                    'cash': str(self.cash),
                    'orders': copy.deepcopy(self.orders),
                    'fills': copy.deepcopy(self.fills)}
        revision = digest(exposure)
        return {'account': self.account, 'experiment_id': self.journal.experiment_id,
                'exposure': exposure, 'exposure_revision': revision,
                'exposure_digest': revision, 'journal_sequence': self.journal.seq}
