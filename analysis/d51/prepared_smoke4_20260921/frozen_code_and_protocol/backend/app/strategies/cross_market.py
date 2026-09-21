import numpy as np

def zscore(current: float, history: list[float], min_samples: int = 30) -> float | None:
    if len(history) < min_samples: return None
    arr = np.asarray(history, dtype=float)
    sd = arr.std(ddof=1)
    if sd == 0: return None
    return float((current - arr.mean()) / sd)
