import math

class SPRT:
    def __init__(self, upper=3.0, lower=-3.0):
        self.upper, self.lower, self.llr = upper, lower, 0.0

    def update(self, p_signal_up: float, p_signal_down: float):
        eps = 1e-9
        self.llr += math.log(max(p_signal_up, eps) / max(p_signal_down, eps))
        if self.llr >= self.upper: return "UP"
        if self.llr <= self.lower: return "DOWN"
        return "WAIT"

    def reset(self): self.llr = 0.0
