"""Deployment entry point for the existing two-kind telemetry producer. No trading."""
import asyncio
import concurrent.futures
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent
SOURCE = RUNTIME / 'source'
sys.path[:0] = [str(SOURCE), str(SOURCE / 'backend'), str(RUNTIME / 'packages')]


def configuration():
    from analysis.d6.real_execution_calibration_v1.core import digest
    config = json.loads((RUNTIME / 'deployment.json').read_text(encoding='utf-8'))
    approval = config['approval']
    if approval['approved'] is not True or approval['source_trust_approved'] is not True:
        raise ValueError('APPROVAL_REQUIRED')
    if digest(approval['policy']) != approval['approved_policy_digest']:
        raise ValueError('POLICY_DIGEST_MISMATCH')
    source_approval = config['time_sources']
    if (source_approval['approved'] is not True
            or source_approval['policy_digest'] != approval['approved_policy_digest']
            or source_approval['authentication'] != 'UNAUTHENTICATED_NTP'
            or source_approval['sources'] != ['time.google.com', 'time.cloudflare.com', 'time.windows.com']):
        raise ValueError('TIME_SOURCE_APPROVAL_REQUIRED')
    return config


async def serve(config, key):
    from analysis.provisioning_clock_candidate import ClockCandidate
    from analysis.provisioning_live_observe import ntp
    from analysis.provisioning_telemetry_signing import TelemetrySigner, run_telemetry, publish_subset
    from analysis.d6.real_execution_calibration_v1.v1_binding import verify
    from app.live.network_readonly import GetOnlyTransport
    from app.live.readonly_book_stream import StreamBook

    now = lambda: time.time_ns() // 1_000_000
    approval = config['approval']
    policy = approval['policy']
    output = Path(config['output'])
    transport = GetOnlyTransport('https://gamma-api.polymarket.com', {'/markets'})
    # Sources are pinned above. Only the original measurement implementation runs.
    def sample_clock():
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            return list(pool.map(ntp, config['time_sources']['sources']))

    while True:
        tasks = []
        stop = asyncio.Event()
        publish_subset(output, {}, now())
        try:
            slug = 'btc-updown-5m-' + str(int(time.time()) // 300 * 300)
            markets = await transport.get_json('/markets', {'slug': slug})
            if len(markets) != 1 or markets[0]['slug'] != slug:
                raise ValueError('MARKET_NOT_UNIQUE')
            market = markets[0]
            def array(value):
                return json.loads(value) if isinstance(value, str) else value
            tokens = array(market['clobTokenIds'])
            outcomes = array(market['outcomes'])
            if len(tokens) != 2 or len(set(tokens)) != 2 or [v.lower() for v in outcomes] != ['up', 'down']:
                raise ValueError('OUTCOME_MAPPING')
            expiry = int(datetime.fromisoformat(market['endDate'].replace('Z', '+00:00')).timestamp() * 1000)
            if expiry <= now():
                raise ValueError('MARKET_EXPIRED')
            stream = StreamBook(slug, market['conditionId'], tokens, expiry, clock=now)
            context = dict(policy['context'], market=market['conditionId'], strategy_hashes=verify())
            signer = TelemetrySigner(policy=policy, approved_digest=approval['approved_policy_digest'],
                key_id='d6-windows-telemetry-v1', key=key, context=context, now=now)
            lease = ClockCandidate(wall_ms=now, monotonic_ms=lambda: time.monotonic_ns() // 1_000_000)
            tasks.append(asyncio.create_task(stream.run(reconnect=False)))
            tasks.append(asyncio.create_task(run_telemetry(signer=signer, stream=stream, lease=lease,
                sample_clock=sample_clock, directory=output, stop=stop)))
            done, _ = await asyncio.wait(tasks, timeout=max(0, (expiry-now())/1000),
                                         return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # No raw exception text, payload, key or credential in the diagnostic.
            print('TELEMETRY_WITHDRAWN:' + type(exc).__name__, flush=True)
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            publish_subset(output, {}, now())
        await asyncio.sleep(1)


def main():
    config = configuration()
    from analysis.d6.real_execution_calibration_v1.v1_binding import verify
    verify()
    if sys.argv[1:] == ['--check-imports']:
        from analysis.provisioning_clock_candidate import ClockCandidate
        from analysis.provisioning_live_observe import ntp
        from analysis.provisioning_telemetry_signing import TelemetrySigner, run_telemetry
        from analysis.provisioning_signed_custody import load_key
        from app.live.readonly_book_stream import StreamBook
        import websockets
        print('ISOLATED_IMPORTS_AND_PINNED_CONFIGURATION_PASS')
        return
    if sys.argv[1:]:
        raise ValueError('NO_CALLER_SUPPLIED_SIGNING_INPUT')
    if (RUNTIME != Path('C:/ProgramData/D6Authority/runtime-v1').resolve()
            or Path(sys.executable).resolve() != (RUNTIME/'python/python.exe').resolve()):
        raise ValueError('PROTECTED_RUNTIME_REQUIRED')
    # Do not inherit caller-controlled TLS roots or proxy endpoints.
    for name in tuple(os.environ):
        if name.upper() in {'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE',
                            'CURL_CA_BUNDLE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'}:
            os.environ.pop(name, None)
    # Existing key ACL validation invokes powershell by name. Its resolution must
    # not inherit a supervisor-controlled PATH under the Authority identity.
    import ctypes
    windows = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetWindowsDirectoryW(windows, len(windows)):
        raise ValueError('WINDOWS_DIRECTORY_UNAVAILABLE')
    system32 = Path(windows.value) / 'System32'
    os.environ['PATH'] = str(system32) + ';' + str(system32/'WindowsPowerShell/v1.0')
    from app.live.l2_windows_storage import WindowsProtection
    from analysis.provisioning_signed_custody import load_key
    platform = WindowsProtection()
    if platform.sid != config['authority_sid']:
        raise ValueError('DEDICATED_AUTHORITY_IDENTITY_REQUIRED')
    if ctypes.windll.shell32.IsUserAnAdmin():
        raise ValueError('NON_ADMIN_AUTHORITY_REQUIRED')
    spec = config['approval']['policy']['keys']['d6-windows-telemetry-v1']
    key = load_key(config['key_file'], spec['address'])
    asyncio.run(serve(config, key))


if __name__ == '__main__':
    main()
