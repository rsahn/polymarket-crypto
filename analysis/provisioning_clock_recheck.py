"""Read-only clock observations; never issues an authority proof or arms D6."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.provisioning_live_observe import ntp

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    samples = [ntp(host) for _ in range(3) for host in
               ('time.google.com', 'time.cloudflare.com', 'time.windows.com')]
    passed = all(s.get('diagnostic_within_100ms') is True for s in samples)
    report = dict(samples=samples, numerical_samples_pass=passed,
                  CLOCK_100MS_QUALIFIED=False, submit_allowed=False,
                  limitation='Unauthenticated diagnostic samples; fresh authority evidence and ongoing monitoring remain required.')
    with Path(args.output).open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report))
    return 0 if passed else 2

if __name__ == '__main__':
    raise SystemExit(main())
