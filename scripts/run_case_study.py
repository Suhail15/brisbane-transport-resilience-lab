"""Portable preparation, execution, export and offline verification of INT-011."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from resilience.pipeline.case_study import CONFIG, prepare, run_date, report, pack, reproduce, refreeze, read_config, load_json
from resilience.pipeline.integrity import sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('prepare', 'refreeze', 'run', 'report', 'pack', 'reproduce'))
    p.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    p.add_argument('--config', type=Path, default=CONFIG)
    p.add_argument('--output', type=Path)
    p.add_argument('--dates', nargs='+')
    p.add_argument('--destination', type=Path)
    p.add_argument('--source-study', type=Path)
    p.add_argument('--allow-registered', action='store_true', help='Use only after explicit coordinator authorization for confirmation/replication')
    p.add_argument('--include-development', action='store_true')
    p.add_argument('--expected-manifest-sha256')
    args = p.parse_args()
    output = args.output or args.data_dir / 'processed' / read_config(args.config)['study_id']
    if args.command in ('run', 'report', 'pack'):
        if load_json(output / 'protocol.json')['config_sha256'] != sha(args.config.read_bytes()):
            raise ValueError('Config differs from frozen protocol; use a separate study directory')
    progress = lambda row: print(json.dumps(row), flush=True)
    if args.command == 'prepare':
        from resilience.pipeline.archive import Archive
        progress(prepare(Archive(args.data_dir), output, args.config, args.dates))
    elif args.command == 'refreeze':
        if not args.source_study:
            p.error('refreeze requires --source-study and coordinator approval')
        if load_json(args.source_study / 'protocol.json')['config_sha256'] != sha(args.config.read_bytes()):
            raise ValueError('Refreeze requires the identical source study --config')
        progress(refreeze(output, args.source_study))
    elif args.command == 'run':
        if not args.dates:
            p.error('run requires --dates')
        for day in args.dates:
            run_date(output, day, allow_registered=args.allow_registered, on_progress=progress)
    elif args.command == 'report':
        progress(report(output, include_development=args.include_development))
    elif args.command == 'pack':
        if not args.destination or not args.dates:
            p.error('pack requires --destination and --dates')
        progress(pack(output, args.destination, args.dates))
    else:
        if not args.destination:
            p.error('reproduce requires --destination')
        reproduce(args.destination, args.expected_manifest_sha256, on_progress=progress)


if __name__ == '__main__':
    main()
