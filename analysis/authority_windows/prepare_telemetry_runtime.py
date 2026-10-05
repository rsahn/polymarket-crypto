"""Stage a public-code-only deployment of the existing telemetry components."""
import hashlib
import importlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]


def prepare(target):
    from packaging.requirements import Requirement
    from analysis.d6.real_execution_calibration_v1.core import digest
    from analysis.d6.real_execution_calibration_v1.v1_binding import verify
    target = target.resolve()
    if target.exists():
        raise ValueError('NEW_STAGING_DIRECTORY_REQUIRED')
    approval = json.loads((ROOT/'analysis/authority_windows/policy-approved-20261004-v1.json').read_text())
    source_approval = json.loads((ROOT/'analysis/authority_windows/time-sources-approved-20261004-v1.json').read_text())
    public = json.loads(Path('C:/ProgramData/D6Authority/out/public-identity.json').read_text(encoding='utf-8-sig'))
    if (approval['approved'] is not True or approval['source_trust_approved'] is not True
            or digest(approval['policy']) != approval['approved_policy_digest']
            or source_approval['approved'] is not True):
        raise ValueError('APPROVAL_REQUIRED')
    verify()
    for name in ('analysis.provisioning_telemetry_signing', 'analysis.provisioning_clock_candidate',
                 'analysis.provisioning_live_observe', 'analysis.provisioning_signed_custody',
                 'app.live.readonly_book_stream', 'websockets.asyncio.client'):
        importlib.import_module(name)
    target.mkdir(parents=True)
    def copy(source, destination):
        if source.is_symlink() or (hasattr(source, 'is_junction') and source.is_junction()):
            raise ValueError('SOURCE_LINK_FORBIDDEN')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    # Only source modules actually imported by these public-only components.
    source_files = set()
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(ROOT) and path.suffix == '.py':
            source_files.add(path.relative_to(ROOT))
    source_files.update(Path(name) for name in verify())
    for relative in sorted(source_files):
        copy(ROOT/relative, target/'source'/relative)
    # Copy the installed dependency distributions, with their installed versions.
    # Wallet SDK, dotenv, user startup files and all credential stores are excluded.
    pending = [('eth-account', frozenset()), ('websockets', frozenset())]
    processed = set()
    distributions = {}
    while pending:
        name, extras = pending.pop()
        marker_key = (name.lower().replace('_', '-'), extras)
        if marker_key in processed:
            continue
        processed.add(marker_key)
        dist = metadata.distribution(name)
        distributions[dist.metadata['Name']] = dist.version
        base = Path(dist.locate_file('')).resolve()
        for file in dist.files or []:
            relative = Path(str(file))
            if '..' in relative.parts or relative.is_absolute() or relative.suffix in ('.pyc', '.pth'):
                continue
            source = Path(dist.locate_file(file)).resolve()
            if not source.is_relative_to(base):
                raise ValueError('DISTRIBUTION_PATH_ESCAPE')
            if source.is_file():
                copy(source, target/'packages'/relative)
        for raw in dist.requires or []:
            requirement = Requirement(raw)
            if requirement.marker and not any(requirement.marker.evaluate({'extra': extra})
                    for extra in ({''} | set(extras))):
                continue
            pending.append((requirement.name, frozenset(requirement.extras)))
    if any('polymarket' in name.lower() or 'dotenv' in name.lower() for name in distributions):
        raise ValueError('FORBIDDEN_DISTRIBUTION')
    prefix = Path(sys.base_prefix)
    python_dir = target/'python'
    python_dir.mkdir()
    for path in prefix.iterdir():
        if path.is_file() and (path.name == 'python.exe' or path.suffix.lower() == '.dll'):
            copy(path, python_dir/path.name)
    for name in ('Lib', 'DLLs'):
        shutil.copytree(prefix/name, python_dir/name,
            ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc', 'test', 'tests', 'idlelib', 'tkinter', 'ensurepip'))
    copy(ROOT/'analysis/authority_windows/telemetry_host.py', target/'telemetry_host.py')
    config = dict(approval=approval, time_sources=source_approval,
        authority_sid=public['authority_sid'], supervisor_sid=public['supervisor_sid'],
        key_file='C:/ProgramData/D6Authority/private/authority-v1.dpapi',
        output='C:/ProgramData/D6Authority/out')
    (target/'deployment.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
    manifest = dict(schema='D6_TELEMETRY_DEPLOYMENT_V1', policy_digest=approval['approved_policy_digest'],
        authority_sid=public['authority_sid'], supervisor_sid=public['supervisor_sid'],
        distributions=distributions, python_version=sys.version, source_modules=[str(x).replace('\\','/') for x in sorted(source_files)],
        files={str(p.relative_to(target)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(target.rglob('*')) if p.is_file()})
    path = target/'manifest.json'
    path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(directory=str(target), manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         files=len(manifest['files']), distributions=distributions)))


if __name__ == '__main__':
    prepare(Path(sys.argv[1]))
