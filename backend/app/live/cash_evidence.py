"""Pure validation of selected ERC20 receipt cash movements, never a live gate.

Input provenance must be supplied by a separately qualified read-only collector.
No RPC, SDK client, secret loading, fee formula or monetary submission is present.
A matching net delta does not prove global history or identify fees/profit.
"""
import re
from .production_readonly import fresh
from .temporal_contract import CASH_EVIDENCE_GUARD_MS

TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'


def _hex(value, size):
    if not isinstance(value,str) or not re.fullmatch('0x[0-9a-fA-F]{'+str(size)+'}',value):
        raise ValueError()
    return value.lower()


def _quantity(value):
    if not isinstance(value,str) or not re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)',value):
        raise ValueError()
    return int(value,16)


def _raw(value):
    if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9][0-9]*)',value):
        raise ValueError()
    result=int(value)
    if result>=2**256:raise ValueError()
    return result


def reconcile_cash_delta(evidence, *, expected_wallet, expected_contract, expected_transactions, now_ms):
    rejected=dict(status='BLOCKED',reason='CASH_EVIDENCE_INVALID',fees_raw=None,pnl_raw=None,
                  current_inventory_proven=False,submit_allowed=False)
    try:
        wallet,contract=_hex(expected_wallet,40),_hex(expected_contract,40)
        if type(evidence['chain_id']) is not int or evidence['chain_id']!=137:raise ValueError()
        if _hex(evidence['wallet'],40)!=wallet or _hex(evidence['collateral_contract'],40)!=contract:raise ValueError()
        if type(now_ms) is not int:raise ValueError()
        before,after=evidence['before'],evidence['after']
        low,high=before['block_number'],after['block_number']
        if type(low) is not int or type(high) is not int or not 0<=low<=high:raise ValueError()
        canonical=evidence['canonical_blocks']
        for observation in (before,after):
            if _hex(canonical[str(observation['block_number'])],64)!=_hex(observation['block_hash'],64):raise ValueError()
        for stamp in (after['observed_ms'],evidence['canonical_observed_ms']):
            if type(stamp) is not int or not fresh(stamp,now_ms,CASH_EVIDENCE_GUARD_MS):raise ValueError()
        start,end=_raw(before['balance_raw']),_raw(after['balance_raw'])
        if not isinstance(expected_transactions,list) or len(expected_transactions)>1000:raise ValueError()
        expected={_hex(tx,64) for tx in expected_transactions}
        if len(expected)!=len(expected_transactions):raise ValueError()
        receipts=evidence['receipts']
        if not isinstance(receipts,list) or len(receipts)!=len(expected):raise ValueError()
        seen=set();log_ids=set();delta=0;transfers=0
        for wrapper in receipts:
            stamp=wrapper['observed_ms']
            if type(stamp) is not int or not fresh(stamp,now_ms,CASH_EVIDENCE_GUARD_MS):raise ValueError()
            receipt=wrapper['receipt'];tx=_hex(receipt['transactionHash'],64)
            block=_quantity(receipt['blockNumber']);block_hash=_hex(receipt['blockHash'],64)
            if tx not in expected or tx in seen or not low<block<=high or receipt['status']!='0x1':raise ValueError()
            if _hex(canonical[str(block)],64)!=block_hash:raise ValueError()
            seen.add(tx)
            logs=receipt['logs']
            if not isinstance(logs,list) or len(logs)>10000:raise ValueError()
            for log in logs:
                if (log.get('removed',False) is not False or _hex(log['transactionHash'],64)!=tx
                    or _quantity(log['blockNumber'])!=block or _hex(log['blockHash'],64)!=block_hash):raise ValueError()
                identity=(block,_quantity(log['logIndex']))
                if identity in log_ids:raise ValueError()
                log_ids.add(identity)
                if _hex(log['address'],40)!=contract:continue
                topics=log['topics']
                if not isinstance(topics,list) or not topics:raise ValueError()
                if _hex(topics[0],64)!=TRANSFER_TOPIC:continue
                if len(topics)!=3:raise ValueError()
                sender,recipient=_hex(topics[1],64),_hex(topics[2],64)
                if sender[2:26]!='0'*24 or recipient[2:26]!='0'*24:raise ValueError()
                amount=int(_hex(log['data'],64),16)
                outgoing=sender[26:]==wallet[2:];incoming=recipient[26:]==wallet[2:]
                delta+=amount*(int(incoming)-int(outgoing))
                transfers+=int(incoming or outgoing)
        if seen!=expected or start+delta!=end:raise ValueError()
        return dict(status='CASH_DELTA_MATCHED',delta_raw=str(delta),after_balance_raw=str(end),
                    from_block=low,to_block=high,receipt_count=len(seen),transfer_count=transfers,
                    scope='SELECTED_RECEIPTS_AND_PINNED_BALANCE_DELTA_NOT_GLOBAL_COMPLETENESS',
                    fees_raw=None,pnl_raw=None,current_inventory_proven=False,submit_allowed=False)
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
        return rejected
