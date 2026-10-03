import asyncio,hashlib,json
from pathlib import Path
import pytest
from .production_provider import EvidenceInbox
from .launch import from_approved_inbox

def inbox(tmp_path):
    # Test the read codec independently of the external-directory eligibility gate.
    p=object.__new__(EvidenceInbox);p.directory=tmp_path;return p

def test_repository_cannot_host_production_evidence_inbox():
    with pytest.raises(ValueError,match='OUTSIDE_GIT'):EvidenceInbox(Path(__file__).resolve().parents[3])

@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}',b'{"a":'])
def test_inbox_rejects_ambiguous_or_partial_json(tmp_path,raw):
    (tmp_path/'snapshot.json').write_bytes(raw)
    with pytest.raises(ValueError):asyncio.run(inbox(tmp_path).snapshot())

def test_inbox_size_bound(tmp_path):
    p=inbox(tmp_path);p.MAX_BYTES=16
    (tmp_path/'snapshot.json').write_bytes(b' '*17)
    with pytest.raises(ValueError,match='EVIDENCE_SIZE'):asyncio.run(p.snapshot())

@pytest.mark.parametrize('name',['../outside','a/b','a\\b','..','C:outside.json','snapshot.json:stream'])
def test_inbox_no_path_traversal(tmp_path,name):
    with pytest.raises(ValueError,match='FILENAME'):inbox(tmp_path).read(name)

def test_execution_inbox_uses_digest_filename(tmp_path):
    order_id='../../arbitrary';name='execution-'+hashlib.sha256(order_id.encode()).hexdigest()+'.json'
    (tmp_path/name).write_text(json.dumps(dict(order_id=order_id)))
    assert asyncio.run(inbox(tmp_path).execution(order_id))==dict(order_id=order_id)

def test_unapproved_policy_cannot_initialize_launch(tmp_path):
    with pytest.raises(ValueError,match='APPROVAL_MISMATCH'):
        asyncio.run(from_approved_inbox(directory=tmp_path,trust_policy={},approved_policy_digest='0'*64,client=None,custody=None))


def test_execution_waits_for_atomic_publication(tmp_path):
    async def case():
        p=inbox(tmp_path);order_id='order'
        task=asyncio.create_task(p.execution(order_id))
        await asyncio.sleep(.01)
        assert not task.done()
        name='execution-'+hashlib.sha256(order_id.encode()).hexdigest()+'.json'
        (tmp_path/name).write_text(json.dumps(dict(order_id=order_id)))
        assert await asyncio.wait_for(task,1)==dict(order_id=order_id)
    asyncio.run(case())

def test_missing_execution_can_be_cancelled(tmp_path):
    async def case():
        with pytest.raises(TimeoutError):await asyncio.wait_for(inbox(tmp_path).execution('missing'),.02)
    asyncio.run(case())
