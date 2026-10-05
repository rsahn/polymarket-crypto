"""Load .env and launch live_runner — avoids exposing key in command line."""
import os, sys, subprocess, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
ENV_FILE = ROOT.parents[2] / '.env'

# Load .env
env = {}
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

# Merge into current env
for k, v in env.items():
    os.environ[k] = v

# No pre-clean needed — custody journal uses tempdir with PID suffix

# Launch
cmd = [sys.executable, '-m', 'analysis.d6.real_execution_calibration_v1.live_runner']
os.chdir(ROOT.parents[2])
sys.exit(subprocess.call(cmd, env=os.environ))
