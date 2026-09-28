import pytest
from app.d5 import store

def test_failed_code_provenance_closes_sqlite_before_rethrow(tmp_path,monkeypatch):
    def fail():raise RuntimeError('PROVENANCE_DENIED_FIXTURE')
    monkeypatch.setattr(store,'code_version',fail)
    path=tmp_path/'fixture.db'
    with pytest.raises(RuntimeError,match='PROVENANCE_DENIED_FIXTURE'):store.Store(path)
    # On Windows this fails while an abandoned SQLite handle still owns the file.
    path.unlink();assert not path.exists()
