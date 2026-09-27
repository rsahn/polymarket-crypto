"""Single-purpose crash fixture; guard installed before project imports."""
import sys,os,socket
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
def guard(event,args):
    if event in ('socket.connect','socket.bind','socket.getaddrinfo','socket.sendto','subprocess.Popen','os.system'):raise RuntimeError('NETWORK_OR_SUBPROCESS_FORBIDDEN')
sys.addaudithook(guard)
from analysis.d6.real_execution_calibration_v1.offline import Simulation
import io
s=Simulation(sys.argv[1],console=io.StringIO());s.cycle('residual')
from analysis.d6.real_execution_calibration_v1.live_logging import LiveLog,LoggedJournal
from analysis.d6.real_execution_calibration_v1.core import CalibrationLedger
folder=Path(sys.argv[1])/'typed-live-fixture'
log=LiveLog(folder,'fixture',console=io.StringIO(),background=False)
log.public_tokens.add('1');log.public_markets.add('0x'+'a'*64)
journal=LoggedJournal(folder/'sealed.jsonl','fixture',log)
ledger=CalibrationLedger(journal,'fixture-account','1')
ledger.seal_shadow('fixture-op',{'market':'0x'+'a'*64,'token':'1','expected_quantity':'1','expected_exit_behavior':{'depth':'password=CRASH_SECRET_CANARY','hold_ms':500}})
ledger.checkpoint()
os._exit(9)
