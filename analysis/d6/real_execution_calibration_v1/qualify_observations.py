"""Explicit bounded qualification entrypoint. --observe permits ONLY audited reads."""
import argparse,asyncio,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from analysis.d6.real_execution_calibration_v1.selection import inspect_selection
from analysis.d6.real_execution_calibration_v1.v1_binding import verify

async def observe(root,selection):
    from app.live.l2_existing_reader import load_existing,EXPECTED
    from polymarket._internal.wallet import classify_account,signature_type_for
    from polymarket._internal.environment import PRODUCTION_CONFIG
    from analysis.d6.real_execution_calibration_v1.observation_collector import build_collector
    from analysis.d6.real_execution_calibration_v1.chain_observer import observe_chain
    creds=None;collector=None
    report=dict(mode='LIVE_READ_ONLY_QUALIFICATION',observed_ms=time.time_ns()//1000000,selection=selection,strategy_hashes=verify(),private_key_loaded=False,credential_creation=False,order_signatures=0,order_submissions=0,ready_for_arm=False,submit_allowed=False,current_inventory_proven=False,operator=dict(designation='requesting-owner',consent_scope='MANUAL_OPERATOR_DESIGNATED_ONLY',specific_exposure_accepted=False,recovery_drill_verified=False))
    try:
        if not selection['selection_ready']:
            report.update(status='BLOCKED_ACCOUNT_SELECTION',mode='NO_NETWORK_SELECTION_GATE',blocker='ACCOUNT_OR_MARKET_SELECTION_CONFLICT',credentials_accessed=False,requests=[]);return report
        wallet=selection['selected_wallet']
        identity=classify_account(signer=EXPECTED,wallet=wallet,config=PRODUCTION_CONFIG.wallet_derivation)
        signature_type=signature_type_for(identity.wallet_type)
        if signature_type not in (0,3):raise ValueError('EXISTING_ACCOUNT_TYPE_UNREVIEWED')
        creds,report['storage']=load_existing(root)
        if not creds:report['blocker']='EXISTING_PROTECTED_L2_UNAVAILABLE_OR_UNSAFE';return report
        collector=build_collector(creds,wallet,EXPECTED,signature_type)
        report['observations']=await collector.collect(selection)
        market=report['observations']['checks'].get('market',{})
        tokens=[market[k] for k in ('token_up','token_down')] if market.get('status')=='OBSERVED' else []
        report['chain']=await asyncio.to_thread(observe_chain,wallet,report['observations']['receipt_candidates'],os.environ.get('POLYGON_ARCHIVE_RPC_URL'),tokens)
        report['requests']=collector.audit
        report['read_budget']=dict(get_calls_admitted=collector.budget.count,get_limit=collector.budget.limit,min_get_interval_ms=250,retries=0,rate_limited=collector.budget.limited)
        report['blockers']=report['observations']['unknowns']
        report['status']='READ_ONLY_OBSERVED_NOT_READY'
    except Exception as exc:
        report['status']='BLOCKED';report['blocker']=type(exc).__name__
        if collector:report['requests']=collector.audit
    finally:
        report['finished_ms']=time.time_ns()//1000000;report['proofs_require_fresh_reacquisition']=True
        if collector:
            for transport in (collector.client.clob,collector.client.data,collector.public,collector.gamma):transport.close()
        if creds:
            encoded=json.dumps(report,default=str)
            if any(value in encoded for value in creds.values()):
                report.clear();report.update(status='BLOCKED_REPORT_SECRET_CANARY',submit_allowed=False)
            creds.clear()
    return report

class Parser(argparse.ArgumentParser):
    def error(self,message):self.exit(2,'INVALID_ARGUMENTS; no secrets accepted on CLI.\n')

def main():
    parser=Parser();parser.add_argument('--observe',action='store_true');parser.add_argument('--account-choice',choices=('configured-eoa','canonical-d6'));args=parser.parse_args()
    selection=inspect_selection(ROOT,account_choice=args.account_choice)
    result=asyncio.run(observe(ROOT,selection)) if args.observe else dict(mode='SELECTION_ONLY',selection=selection,submit_allowed=False)
    folder=Path(__file__).parent/'evidence'/('readonly_'+str(time.time_ns()//1000000));folder.mkdir(parents=True,exist_ok=False)
    target=folder/'qualification_matrix.json'
    with target.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2,default=str);handle.write('\n');handle.flush();os.fsync(handle.fileno())
    print(json.dumps({'artifact':str(target),'status':result.get('status',result.get('blocker','SELECTION_ONLY')),'submit_allowed':False}))

if __name__=='__main__':main()
