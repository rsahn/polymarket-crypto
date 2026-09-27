import asyncio,pytest
from .drill_host import DrillChannel,DrillHost
from .core import digest
class Platform:
    sid='FIXTURE-SID'
    def create_private_directory(self,p):p.mkdir()
def host(tmp_path):return DrillHost(DrillChannel(tmp_path/'DRILL-NO-MONEY',platform=Platform(),acl=lambda p,s:None,clock=lambda:1000))
def test_drill_recovery_change_replay_and_no_automatic_acceptance(tmp_path):
    async def run():
        h=host(tmp_path);h.init();r=h.request();h.channel.challenge(r)
        assert (await h.tick())['status']=='UNACCEPTED'
        recovered=DrillHost(h.channel);assert recovered.request()==r
        recovered.change();assert recovered.request()!=r
        assert not await h.verifier.verify({'challenge_id':digest(r)},recovered.request())
        assert not list(h.directory.glob('*.receipt.json'))
        with pytest.raises(ValueError,match='ALREADY_EXISTS'):h.init()
    asyncio.run(run())

def test_drill_monitor_cancellation_keeps_recovery_and_unaccepted(tmp_path):
    async def run():
        h=host(tmp_path);h.init();t=asyncio.create_task(h.monitor());await asyncio.sleep(.02);t.cancel()
        with pytest.raises(asyncio.CancelledError):await t
        assert h.state()['monitor_stopped'] and h.state()['status']=='UNACCEPTED' and h.state()['monitor_ticks']>=1
        assert not list(h.directory.glob('*.receipt.json'))
    asyncio.run(run())

def test_drill_refuses_production_request(tmp_path):
    h=host(tmp_path);h.init();r=h.request();r['account']='REAL'
    with pytest.raises(ValueError,match='DRILL_ONLY'):h.channel.challenge(r)
