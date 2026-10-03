from pathlib import Path
from protected_book_migration import *
def test_only_exact_additive_metadata_migration_reconstructs_historical_source():
    # Retain the historical proof against its exact archived bytes. The current
    # reconnect implementation is a new revision, not an additive migration.
    root=Path(__file__).resolve().parents[2]
    data=(root/'backend/tests/fixtures/readonly_book_stream_legacy.txt').read_bytes()
    assert protected_match(NAME,data,OLD)
    restored=data.replace(DELTA,b'',1)
    assert hashlib.sha256(restored).hexdigest()==OLD
    assert protected_match(NAME,restored,OLD)
    assert not protected_match(NAME,(root/NAME).read_bytes(),OLD)
def test_mutating_any_control_or_delta_does_not_get_blessed():
    data=(Path(__file__).resolve().parents[2]/NAME).read_bytes()
    assert not protected_match(NAME,data+b'\n',OLD)
    assert not protected_match(NAME,data.replace(b'receive_ms',b'anything_x',1),OLD)
    assert not protected_match(NAME,data,NEW+'x')
    assert not protected_match('backend/app/live/risk.py',data,OLD)
