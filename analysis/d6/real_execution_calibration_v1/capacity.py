"""A bounded 72h production profile; storage is checked before arming.

Two reconciliation records/second, 864 rotations with 32 records each,
4096 order/incident records. 16 KiB maximum sealed record, plus 50% margin.
Unbounded incident storms still fail closed at the quotas.
"""
import shutil
SECONDS=259200
RECORDS=2*SECONDS+864*32+4096
MAX_RECORD_BYTES=16*1024
PROJECTED_BYTES=RECORDS*MAX_RECORD_BYTES
PROJECTED_LOG_BYTES=RECORDS*(MAX_RECORD_BYTES+256)
QUOTA_BYTES=16*1024**3
RESERVE_BYTES=1024**3
REQUIRED_FREE_BYTES=2*QUOTA_BYTES+RESERVE_BYTES
assert QUOTA_BYTES>=PROJECTED_LOG_BYTES*3//2

def require_capacity(directory):
    if shutil.disk_usage(directory).free<REQUIRED_FREE_BYTES:
        raise ValueError('STORAGE_72H_CAPACITY_UNPROVEN')
    return dict(seconds=SECONDS,max_records=RECORDS,max_record_bytes=MAX_RECORD_BYTES,projected_journal_bytes=PROJECTED_BYTES,projected_log_bytes=PROJECTED_LOG_BYTES,quota_bytes_per_sink=QUOTA_BYTES,required_free_bytes=REQUIRED_FREE_BYTES)
