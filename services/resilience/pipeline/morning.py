"""Frozen, source-only final-morning targets and resumable experiment orchestration."""
from __future__ import annotations

import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter
from ..contracts import JourneyRequest, Scenario
from .analysis import canonical, digest, prepare_input, available_requests
from .files import atomic_write
from .journey_set import expand
from .snapshots import load_snapshot
from .sensitivity import stress_snapshot

CONFIG = Path('configs/morning-evaluation.v1.json')
DATES = ('2026-10-19', '2026-10-20', '2026-10-21')
SCENARIOS = ('cancellation', 'stop_closure', 'rail_corridor', 'bus_delay')
TERMINAL = ('completed', 'failed', 'cancelled')


class UnsupportedTarget(ValueError):
    """Required source-selected scenario target is absent; never substitute it."""


def read_plan(path, config):
    plan = json.loads(Path(path).read_text())
    ids = plan.get('decision_snapshots')
    if not isinstance(ids, dict) or set(ids) != set(DATES):
        raise ValueError('manifest decision_snapshots must contain exactly the three fixed final dates')
    if tuple(config['evaluation_dates']) != DATES or tuple(config['scenarios']) != SCENARIOS:
        raise ValueError('fixed evaluation dates/scenarios changed; coordinator review required')
    if len(set(ids.values())) != len(DATES) or not all(isinstance(v, str) and v for v in ids.values()):
        raise ValueError('each final date requires a distinct explicit snapshot ID')
    return plan


def target_manifest(snapshot, date, config):
    local = snapshot.metadata.snapshot_at.astimezone(ZoneInfo(config['timezone']))
    if (local.date().isoformat() != date or snapshot.metadata.service_date.isoformat() != date
            or local.strftime('%H:%M:%S') != config['decision_local_time'] or local.microsecond):
        raise ValueError(f'{date}: snapshot must be at the fixed local decision cutoff')
    future = sorted((c for c in snapshot.connections if c.departure_s >= snapshot.metadata.snapshot_s),
                    key=lambda c: (c.departure_s, c.connection_id))
    bus = next((c for c in future if c.mode == 'bus' and c.from_stop_id in config['corridor_bus_origin_ids']), None)
    rail = next((c for c in future if c.mode == 'rail' and
                 (c.from_stop_id in config['rail_origin_ids'] or c.to_stop_id in config['rail_destination_ids'])), None)
    closed = config['closed_stop_id']
    supported_stop = any(s.stop_id == closed for s in snapshot.stops)
    missing = [name for name, present in (('corridor_bus', bus is not None), ('rail_movement', rail is not None),
                                        ('closed_stop:' + closed, supported_stop)) if not present]
    start = snapshot.metadata.snapshot_s
    common = {'start_s': start, 'end_s': start + config['scenario_duration_seconds']}
    def scenario(kind, name, **fields):
        return dict(common, kind=kind, scenario_id=f'morning:{date}:{name}', **fields)
    examples = {
        'cancellation': scenario('trip_cancellation', 'cancel', trip_instance_ids=[bus.trip_instance_id]) if bus else None,
        'stop_closure': scenario('stop_unavailable', 'stop', stop_ids=[closed]) if supported_stop else None,
        'rail_corridor': scenario('corridor_closure', 'rail', segments=[{'from_stop_id': rail.from_stop_id,
            'to_stop_id': rail.to_stop_id, 'bidirectional': True}]) if rail else None,
        'bus_delay': scenario('additional_delay', 'delay', trip_instance_ids=[bus.trip_instance_id],
            additional_seconds=config['additional_bus_delay_seconds']) if bus else None,
    }
    requests = [r.model_dump(mode='json') for r in expand(snapshot)]
    if len(requests) != 100 or len({(r['origin_stop_id'], r['destination_stop_id']) for r in requests}) != 20:
        raise ValueError('frozen journey set must retain 100 requests over 20 OD pairs')
    return {'version': config['version'], 'date': date, 'snapshot_id': snapshot.metadata.snapshot_id,
            'snapshot_at': snapshot.metadata.snapshot_at.isoformat(), 'config_sha256': digest(config),
            'journey_set_sha256': digest(json.loads(Path(config['journey_set']).read_text())),
            'source_record_ids': sorted(s.record_id for s in snapshot.metadata.sources),
            'targets': {'bus': bus.model_dump(mode='json') if bus else None,
                        'rail': rail.model_dump(mode='json') if rail else None,
                        'closed_stop_id': closed if supported_stop else None},
            'unsupported_targets': missing, 'status': 'unsupported_target' if missing else 'prepared',
            'requests': requests, 'request_set_sha256': digest(requests), 'scenarios': examples,
            'classification': 'Recorded morning inputs; disruptions and recovery are hypothetical',
            'selection': 'Earliest future bus at configured origin; rail at configured origin OR destination; departure/id order'}


def prepare_manifests(archive, plan, config):
    """Freeze every final date before any execution, including explicit null targets."""
    root = archive.root / 'processed' / config['version']
    atomic_write(root / 'plan.json', canonical({'plan': plan, 'config': config,
                 'plan_sha256': digest(plan), 'config_sha256': digest(config)}), immutable=True)
    manifests = {}
    for date in DATES:
        snapshot = load_snapshot(archive, plan['decision_snapshots'][date])
        manifest = target_manifest(snapshot, date, config)
        manifest['plan_sha256'] = digest(plan)
        manifest['snapshot_content_sha256'] = __import__('hashlib').sha256(
            (archive.root / 'processed' / 'snapshots' / f'{snapshot.metadata.snapshot_id}.json').read_bytes()).hexdigest()
        atomic_write(root / 'targets' / f'{date}.json', canonical(manifest), immutable=True)
        manifests[date] = manifest
    if any(m['unsupported_targets'] for m in manifests.values()):
        raise UnsupportedTarget('Unsupported source targets; inspect immutable targets/*.json; no policies submitted')
    return manifests


def experiment_payloads(manifest, config, scenario_filter=None):
    for name in SCENARIOS:
        if scenario_filter and name not in scenario_filter:
            continue
        for budget, delta in [(b, 0) for b in config['budgets_bus_hours']] + (
                [(config['sensitivity_budget_bus_hours'], d) for d in config['sensitivity_seconds'] if d != 0]
                if name == config['sensitivity_scenario'] else []):
            yield name, {'snapshot_id': manifest['snapshot_id'], 'requests': manifest['requests'],
                'scenarios': [manifest['scenarios'][name]], 'budget_bus_hours': budget,
                'journey_set_version': config['journey_set_version'],
                'bus_running_time_sensitivity_seconds': delta, 'max_swap_evaluations': config['max_swap_evaluations']}


def expected_input(archive, payload):
    """Mirror API normalization to require exact input hashes when resuming."""
    from ..engine import generate_recovery_candidates
    snapshot = load_snapshot(archive, payload['snapshot_id'])
    requests = tuple(JourneyRequest.model_validate(r) for r in payload['requests'])
    scenarios = tuple(TypeAdapter(Scenario).validate_python(s) for s in payload['scenarios'])
    valid, _ = available_requests(snapshot, requests)
    candidates = generate_recovery_candidates(snapshot, valid, scenarios) if valid else ()
    delta = payload['bus_running_time_sensitivity_seconds']
    effective, transform = stress_snapshot(snapshot, delta)
    derived = None
    if delta:
        sha = digest(effective)
        derived = dict(transform, snapshot_content_sha256=sha, path=f'derived-inputs/{sha}.json')
    normalized, _ = prepare_input(archive, snapshot, requests, scenarios, candidates, payload['budget_bus_hours'],
        journey_set_version=payload['journey_set_version'], delta=delta, derived=derived,
        max_swaps=payload['max_swap_evaluations'])
    return normalized


def verify_run(run, expected, run_id):
    if run.get('run_id') != run_id or run.get('input') != expected or run.get('metadata', {}).get('input_sha256') != digest(expected):
        raise ValueError(f'{run_id}: resume input/ID/hash mismatch')


def execute(archive, manifests, config, client, url, dates=None, scenarios=None, poll_seconds=.5):
    root = archive.root / 'processed' / config['version']
    if set(manifests) != set(DATES):
        raise ValueError('all final-date manifests must be frozen before execution')
    selected_dates = DATES if dates is None else tuple(dates)
    if not set(selected_dates) <= set(DATES) or (scenarios and not set(scenarios) <= set(SCENARIOS)):
        raise ValueError('execution filters cannot select dates or scenarios outside the fixed plan')
    summary_path = root / 'summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    for date in selected_dates:
        for name, payload in experiment_payloads(manifests[date], config, scenarios):
            key = f"{date}.{name}.b{payload['budget_bus_hours']}.s{payload['bus_running_time_sensitivity_seconds']}"
            progress_path = root / 'progress' / f'{key}.json'
            final_path = root / 'results' / f'{key}.json'
            expected = expected_input(archive, payload)
            expected_hash = digest(expected)
            progress = json.loads(progress_path.read_text()) if progress_path.exists() else None
            cached_final = None
            if final_path.exists():
                final = json.loads(final_path.read_text())
                verify_run(final, expected, final['run_id'])
                if final['status'] != 'completed':
                    raise RuntimeError(f'{key}: previous terminal {final["status"]}; inspect saved evidence')
                run_id = final['run_id']
                cached_final = final
            elif progress:
                if progress['payload'] != payload or progress['input_sha256'] != expected_hash:
                    raise ValueError(f'{key}: saved progress differs from expected input')
                run_id = progress['run_id']
            else:
                # Recover submission interrupted before the local progress write using exact input identity.
                matching = []
                for path in (archive.root / 'processed' / 'experiments').glob('*.json'):
                    record = json.loads(path.read_text())
                    if record.get('metadata', {}).get('input_sha256') == expected_hash:
                        verify_run(record, expected, record['run_id']); matching.append(record)
                if any(r['status'] in ('failed', 'cancelled') for r in matching):
                    atomic_write(root / 'failures' / f'{key}.json', canonical(matching), immutable=True)
                    raise RuntimeError(f'{key}: prior failed/cancelled exact input; inspect evidence before retry')
                if len(matching) > 1:
                    raise ValueError(f'{key}: multiple exact runs; coordinator reconciliation required')
                if matching:
                    run_id = matching[0]['run_id']
                else:
                    response = client.post(url.rstrip('/') + '/experiments', json=payload)
                    response.raise_for_status(); run_id = response.json()['run_id']
            progress = {'key': key, 'run_id': run_id, 'payload': payload, 'input_sha256': expected_hash}
            atomic_write(progress_path, canonical(progress))
            while True:
                if cached_final is None:
                    response = client.get(url.rstrip('/') + '/experiments/' + run_id)
                    response.raise_for_status(); run = response.json()
                else:
                    run = cached_final
                verify_run(run, expected, run_id)
                atomic_write(progress_path, canonical(dict(progress, status=run['status'], progress=run.get('progress'))))
                if run['status'] in TERMINAL:
                    atomic_write(final_path, canonical(run), immutable=True)
                    result = run.get('result')
                    summary[key] = {'run_id': run_id, 'input_sha256': expected_hash, 'status': run['status'],
                        'date': date, 'scenario': name, 'budget_bus_hours': payload['budget_bus_hours'],
                        'sensitivity_seconds': payload['bus_running_time_sensitivity_seconds'],
                        'request_count': len(payload['requests']), 'error': run.get('error'),
                        'metrics': result['plan']['evaluation']['metrics'] if result else None,
                        'objective': result['plan']['objective'] if result else None,
                        'considered_candidate_ids': result.get('considered_candidate_ids') if result else None}
                    atomic_write(summary_path, canonical(summary))
                    print(json.dumps(dict(key=key, **summary[key])), flush=True)
                    if run['status'] != 'completed':
                        raise RuntimeError(f'{key}: {run["status"]}; saved evidence; automatic retries disabled')
                    break
                time.sleep(poll_seconds)
    return summary
