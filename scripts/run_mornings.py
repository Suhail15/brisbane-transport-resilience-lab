"""Prepare frozen morning targets, then resumably execute the approved final plan."""
import argparse
import json
from pathlib import Path
import sys

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services'))
from resilience.pipeline.archive import Archive
from resilience.pipeline.morning import CONFIG, DATES, SCENARIOS, read_plan, prepare_manifests, execute
from resilience.settings import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, help='JSON with explicit decision_snapshots mapping for all three final dates')
    parser.add_argument('--url', default='http://127.0.0.1:8000/v1')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--date', choices=DATES)
    parser.add_argument('--scenario', choices=SCENARIOS, action='append')
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    plan = read_plan(args.manifest, config)
    archive = Archive(settings.data_dir)
    manifests = prepare_manifests(archive, plan, config)
    print(json.dumps({'prepared_dates': list(manifests), 'requests_per_date': 100}), flush=True)
    if not args.prepare_only:
        with httpx.Client(timeout=120) as client:
            execute(archive, manifests, config, client, args.url,
                    dates=[args.date] if args.date else None, scenarios=args.scenario)


if __name__ == '__main__':
    main()
