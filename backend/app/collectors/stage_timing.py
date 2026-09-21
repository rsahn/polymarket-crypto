"""Bounded diagnostic counters; never a market timestamp or admission rule."""
import time


class StageTiming:
    def __init__(self):
        self.stages = {}

    def start(self):
        return time.perf_counter_ns(), time.thread_time_ns()

    def finish(self, stage, started):
        wall = time.perf_counter_ns() - started[0]
        cpu = time.thread_time_ns() - started[1]
        row = self.stages.setdefault(stage, dict(calls=0, wall_ns=0, cpu_ns=0,
                                                max_wall_ns=0, over_5ms=0, over_50ms=0))
        row['calls'] += 1
        row['wall_ns'] += wall
        row['cpu_ns'] += cpu
        row['max_wall_ns'] = max(row['max_wall_ns'], wall)
        row['over_5ms'] += wall > 5_000_000
        row['over_50ms'] += wall > 50_000_000

    def snapshot(self):
        return {name: dict(row) for name, row in self.stages.items()}
