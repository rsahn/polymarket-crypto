import json
from pathlib import Path
import pytest
from analysis.d6.prospective_24h_v1.protocol import *
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).parent

def test_duration_and_embargo():
 b=boundaries(1000)
 assert b['TRAIN']['end_ms']==1000+43200000
 assert b['VALIDATION']['end_ms']==1000+64800000
 assert b['OOS']['end_ms']==1000+86400000
 assert b['OOS']['eligible_from_ms']==1000+64800000+60000

def test_whole_market_and_feature_label_purge():
 p=plan(0);t=43200000
 assert p.classify(t-300000,t,t-300000,t)=='TRAIN'
 assert p.classify(t-1000,t+299000,t-1000,t+299000)=='PURGED'
 assert p.classify(t,t+300000,t,t+300000)=='PURGED'
 assert p.classify(t+300000,t+600000,t+300000,t+600000)=='VALIDATION'
 assert p.classify(t+60000,t+360000,t+59999,t+360000)=='PURGED'
 assert p.classify(t-300000,t,t-300000,t+1)=='PURGED'

def test_criteria_preserved_except_duration_version_rationale():
 old=json.loads((ROOT/'analysis/d6/prospective_v1/criteria.json').read_text())
 new=json.loads((HERE/'criteria.json').read_text())
 assert old['duration_hours']==[72,48,48] and new['duration_hours']==[12,6,6]
 assert old['version']!=new['version']
 for k,v in old.items():
  if k not in ('duration_hours','version'):assert new[k]==v

def test_impossible_samples_not_relaxed():
 c=json.loads((HERE/'criteria.json').read_text());r=sample_feasibility(c)
 assert all(v['verdict']=='INCONCLUSIVE_INSUFFICIENT_SAMPLE' for v in r.values())
 assert r['TRAIN']['max_active_6h_blocks']==2
 assert 'INSUFFICIENT_SENSITIVITY_BLOCK_HOURS' in r['TRAIN']['reasons']
 assert 'INSUFFICIENT_BLOCK_HOURS' in r['OOS']['reasons']

def test_unbound_manifest_and_exclusive_prepare(tmp_path):
 d=tmp_path/'freeze';m=prepare(d,ROOT)
 assert m['T0'] is None and m['partition_boundaries'] is None
 assert m['dataset_identity'] is None and m['collector_identity'] is None
 assert m['hours']==[12,6,6] and m['NOT_LONG_HORIZON_STABILITY_PROOF']
 assert not m['real_partition_loader_enabled'] and not m['submit_allowed']
 assert verify_preparation(d,ROOT)==m
 with pytest.raises(FileExistsError):prepare(d,ROOT)
 (d/'MANIFEST.json').write_text('{}')
 with pytest.raises(ValueError,match='MANIFEST_CHANGED'):verify_preparation(d,ROOT)

def test_source_causal_requirements_and_incomplete_history():
 e={k:True for k in REQUIRED_SOURCE_PROOFS};assert not source_reasons(e)
 for k in REQUIRED_SOURCE_PROOFS:
  bad=e.copy();bad[k]=None;assert k in source_reasons(bad)
  bad[k]='true';assert k in source_reasons(bad)
 assert 'actual_entry_state' in source_reasons({'full_depth':True,'continuous_24h':True})

def test_storage_24h_unknowns_are_not_zero():
 r=storage(10**12)
 assert r['ARCHIVE_24H_BYTES']==21999279027
 assert r['status']=='STORAGE_24H_UNQUALIFIED'
 assert r['QUALIFIED_24H_REQUIRED_SPACE'] is None and r['ADDITIONAL_SPACE_REQUIRED'] is None
 assert storage(10**12,0,0,0)['QUALIFIED_24H_REQUIRED_SPACE']==26399134833
 assert storage(1,0,0,0)['ADDITIONAL_SPACE_REQUIRED']==26399134832
 with pytest.raises(ValueError):storage(100,-1,0,0)

def test_synthetic_rate_not_replay_qualification():
 r=replay_status({'restart_qualified':True,'marks_per_second':4144,'books_per_second':2215})
 assert r['status']=='REPLAY_24H_UNQUALIFIED' and 'full_event_mix' in r['missing']

def test_oos_first_access_unchanged(tmp_path):
 from analysis.d6.prospective_v1.core import AccessGate as Original
 assert AccessGate is Original
 seal=Seal.create(ROOT,['analysis/d6/prospective_24h_v1/criteria.json']);g=AccessGate(tmp_path,ROOT,seal,'synthetic')
 with pytest.raises(ValueError):g.open('OOS','synthetic',{})
 g.open('TRAIN','synthetic',{});g.finish('TRAIN','PASS',{})
 g.open('VALIDATION','synthetic',{});g.finish('VALIDATION','PASS',{})
 g.open('OOS','synthetic',{})
 with pytest.raises(FileExistsError):g.open('OOS','synthetic',{})

def test_inconclusive_train_blocks_next(tmp_path):
 seal=Seal.create(ROOT,['analysis/d6/prospective_24h_v1/criteria.json']);g=AccessGate(tmp_path,ROOT,seal,'synthetic')
 g.open('TRAIN','synthetic',{});g.finish('TRAIN','INCONCLUSIVE',{'reason':'INCONCLUSIVE_INSUFFICIENT_SAMPLE'})
 with pytest.raises(ValueError):g.open('VALIDATION','synthetic',{})
