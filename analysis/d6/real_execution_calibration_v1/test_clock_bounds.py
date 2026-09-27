import pytest
from .clock_bounds import offset_interval

def args():return dict(send_ms=10000,receive_ms=10020,stamp_ms=10010,quantum_ms=2,quantization='NEAREST_WITH_KNOWN_QUANTUM',source_accuracy_ms=5,local_read_error_ms=1,generation_contract='TIMESTAMP_GENERATED_WITHIN_REQUEST_NO_CACHE')

def test_fine_numeric_interval_is_not_a_source_certificate():
    r=offset_interval(**args())
    assert (r['offset_lower_ms'],r['offset_upper_ms'])==(-17,17) and r['meets_existing_100ms_math_bound'] and not r['clock_qualified']

def test_second_quantization_is_resolution_not_drift():
    r=offset_interval(**{**args(),'receive_ms':10320,'stamp_ms':10000,'quantum_ms':1000,'quantization':'ERROR_AT_MOST_ONE_QUANTUM','source_accuracy_ms':0,'local_read_error_ms':0})
    assert r['offset_lower_ms']==-1320 and r['offset_upper_ms']==1000 and not r['meets_existing_100ms_math_bound']

@pytest.mark.parametrize('change',[{'quantization':'UNKNOWN'},{'source_accuracy_ms':None},{'source_accuracy_ms':True},{'generation_contract':'CACHED_OR_UNKNOWN'},{'receive_ms':9999},{'local_read_error_ms':-1}])
def test_unproven_precision_or_time_contract_cannot_pass(change):
    with pytest.raises(ValueError):offset_interval(**{**args(),**change})
