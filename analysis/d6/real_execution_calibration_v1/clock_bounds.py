"""Pure interval arithmetic, not a clock qualification or network sampler."""
from .binding_consumer import require

def offset_interval(*,send_ms,receive_ms,stamp_ms,quantum_ms,quantization,source_accuracy_ms,local_read_error_ms,generation_contract):
    require(all(type(x) is int for x in (send_ms,receive_ms,stamp_ms,quantum_ms,source_accuracy_ms,local_read_error_ms)),'CLOCK_BOUND_INPUTS_UNKNOWN')
    require(0<=send_ms<=receive_ms and stamp_ms>=0 and quantum_ms>0 and source_accuracy_ms>=0 and local_read_error_ms>=0,'CLOCK_BOUND_RANGE')
    require(generation_contract=='TIMESTAMP_GENERATED_WITHIN_REQUEST_NO_CACHE','TIMESTAMP_GENERATION_OR_CACHE_UNKNOWN')
    if quantization=='FLOOR':low,high=stamp_ms,stamp_ms+quantum_ms
    elif quantization=='NEAREST_WITH_KNOWN_QUANTUM':
        require(quantum_ms%2==0,'EXACT_HALF_QUANTUM_REQUIRED');low,high=stamp_ms-quantum_ms//2,stamp_ms+quantum_ms//2
    elif quantization=='ERROR_AT_MOST_ONE_QUANTUM':low,high=stamp_ms-quantum_ms,stamp_ms+quantum_ms
    else:raise ValueError('QUANTIZATION_ERROR_UNKNOWN')
    extra=source_accuracy_ms+local_read_error_ms
    lower,upper=low-receive_ms-extra,high-send_ms+extra
    return dict(offset_lower_ms=lower,offset_upper_ms=upper,worst_absolute_error_ms=max(abs(lower),abs(upper)),meets_existing_100ms_math_bound=max(abs(lower),abs(upper))<=100,source_contract_required=True,clock_qualified=False,submit_allowed=False)
