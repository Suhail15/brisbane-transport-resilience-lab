"""Registered, additive corridor experiment; no live services or archive mutations.

Inputs and cell outputs are immutable. Preparation may inspect source receipts on
all registered dates; recovery execution defaults to development dates only.
"""
from __future__ import annotations

import json
import math
import tempfile
import time
from collections import OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..contracts import (CorridorClosure, CorridorSegment, JourneyRequest,
                         RecoveryCandidate, RouteResult, TimetableSnapshot)
from ..engine import apply_scenarios, generate_recovery_candidates
from ..engine.recovery import _Search, _plan_key
from ..engine.routing import route_many
from .analysis import ROOT, available_requests, canonical, digest
from .files import atomic_write
from .integrity import sha, verify_manifest_files
from .sensitivity import stress_snapshot

VERSION = 'corridor-impact-staggered-v1'
SCORING_VERSION = 'whole-source-trips-capped-horizon-v1'
CONFIG = ROOT / 'configs/corridor-impact.v2.json'
_FULL_ROUTE_CACHE = OrderedDict()


def code_files():
    return [ROOT / 'services/resilience/contracts.py', ROOT / 'scripts/run_case_study.py',
            *sorted((ROOT / 'services/resilience/engine').glob('*.py')),
            *[ROOT / 'services/resilience/pipeline' / name for name in
              ('case_study.py', 'analysis.py', 'sensitivity.py', 'files.py', 'integrity.py',
               'case_network.py', 'snapshots.py', 'schedule.py', 'walking.py', 'archive.py')],
            ROOT / 'configs/station-access-network.v1.json', ROOT / 'configs/pilot.json']


def code_hash():
    return sha(b''.join(p.relative_to(ROOT).as_posix().encode() + b'\0' +
                        p.read_bytes() + b'\0' for p in code_files()))


def write_json(path, value):
    atomic_write(path, canonical(value), immutable=True)


def load_json(path):
    return json.loads(Path(path).read_bytes())


def diagnostic_json(value):
    """Existing walking diagnostics use infinity for unavailable paths.

    Preserve their location explicitly while emitting standards-compliant JSON;
    this only projects diagnostics and never changes snapshot/routing values.
    """
    unsupported = []
    def clean(item, path):
        if isinstance(item, float) and not math.isfinite(item):
            unsupported.append(path)
            return None
        if isinstance(item, dict):
            return {k: clean(v, path + '/' + k) for k, v in item.items()}
        if isinstance(item, list):
            return [clean(v, path + '/' + str(i)) for i, v in enumerate(item)]
        return item
    result = clean(value, '')
    result['undefined_diagnostic_values'] = {'encoding': 'null', 'count': len(unsupported), 'paths': unsupported}
    return result


def read_config(path=CONFIG):
    config = load_json(path)
    if config['study_id'] not in ('corridor-impact-v1', 'corridor-impact-v2') or config['schema_version'] != 1:
        raise ValueError('Unapproved study schema')
    if config['study_id'] == 'corridor-impact-v2' and config.get('network_config') != 'configs/station-access-network.v1.json':
        raise ValueError('Version 2 requires the approved station-access source network')
    return config


def primary_requests(snapshot, config):
    return tuple(JourneyRequest(
        request_id=f"{VERSION}:{origin}:{destination}:{offset}",
        origin_stop_id=origin, destination_stop_id=destination,
        departure_s=snapshot.metadata.snapshot_s + offset)
        for a in config['primary_station_platforms']
        for b in config['primary_station_platforms'] if a['station'] != b['station']
        for origin in a['stop_ids'] for destination in b['stop_ids']
        for offset in config['offset_seconds'])


def control_requests(snapshot, config):
    control = load_json(ROOT / config['control_journey_set'])
    return tuple(JourneyRequest(
        request_id=f"{control['version']}:{pair['pair_id']}:{offset}",
        origin_stop_id=pair['origin_stop_id'], destination_stop_id=pair['destination_stop_id'],
        departure_s=snapshot.metadata.snapshot_s + offset)
        for pair in control['pairs'] for offset in control['offset_seconds'])


def section_scenario(snapshot, config):
    names = {s.stop_id: s.name.split(' station, platform ')[0]
             for s in snapshot.stops if ' station, platform ' in s.name}
    required = set(config['section_station_names'])
    if not required <= set(names.values()):
        raise ValueError('Required section station absent in retained source')
    edges = sorted({(c.from_stop_id, c.to_stop_id) for c in snapshot.connections
                    if c.mode == 'rail' and names.get(c.from_stop_id) in required
                    and names.get(c.to_stop_id) in required
                    and names[c.from_stop_id] != names[c.to_stop_id]})
    if not edges:
        raise ValueError('No source-supported section movements')
    scenario = CorridorClosure(scenario_id=VERSION + ':rail-section',
        start_s=snapshot.metadata.snapshot_s,
        end_s=snapshot.metadata.snapshot_s + config['closure_duration_seconds'],
        segments=tuple(CorridorSegment(from_stop_id=a, to_stop_id=b,
                                       bidirectional=False) for a, b in edges))
    impact = apply_scenarios(snapshot, (scenario,)).impact
    modes = {c.trip_instance_id: c.mode for c in snapshot.connections}
    if not impact.cancelled_trip_instance_ids or any(
            modes[t] != 'rail' for t in impact.cancelled_trip_instance_ids):
        raise ValueError('Section must cancel nonempty rail-only source trips')
    return scenario


def routes(snapshot, requests):
    # Pure memoization of exact full timetable/request content, never the scoring copy.
    key = (digest(snapshot), digest([r.model_dump(mode='json') for r in requests]))
    if key in _FULL_ROUTE_CACHE:
        _FULL_ROUTE_CACHE.move_to_end(key)
        return _FULL_ROUTE_CACHE[key]
    valid, missing = available_requests(snapshot, requests)
    values = route_many(snapshot, valid) if valid else ()
    by_id = {r.request.request_id: r for r in values}
    by_id.update({r.request_id: RouteResult(request=r, reachable=False,
        quality=snapshot.metadata.quality.model_copy(update={'warnings':
            snapshot.metadata.quality.warnings + ('Adapter unavailable source stop; denominator retained',)}))
        for r in missing})
    result = tuple(by_id[r.request_id] for r in requests)
    _FULL_ROUTE_CACHE[key] = result
    if len(_FULL_ROUTE_CACHE) > 48:
        _FULL_ROUTE_CACHE.popitem(last=False)
    return result


def scoring_snapshot(snapshot, requests, scenarios, candidates):
    """Decision30: keep complete trips, with deterministic reference witnesses.

    Nonnegative journey times mean a departure after the latest query's 90-minute
    cap cannot improve any capped objective or 60-minute restoration. Complete
    retained trips preserve source topology and whole-trip scenario semantics.
    Candidate/scenario witnesses retain feasibility checks even beyond the cap.
    Published itineraries are always recomputed against the full timetable.
    """
    cutoff = max(r.departure_s for r in requests) + 5400
    trips = defaultdict(list)
    for c in snapshot.connections:
        trips[c.trip_instance_id].append(c)
    retained = {tid for tid, cs in trips.items() if any(c.departure_s <= cutoff for c in cs)}
    pairs = {p.pair_id: p for p in snapshot.recovery_pairs}
    candidate_witnesses, scenario_witnesses = [], []
    for pair_id in sorted({c.pair_id for c in candidates}):
        pair = pairs[pair_id]
        for pattern in (pair.outbound, pair.inbound):
            witnesses = []
            for tid in pattern.source_trip_instance_ids:
                trip = sorted(trips.get(tid, ()), key=lambda c: c.sequence)
                if (trip and all(c.mode == 'bus' and c.route_id == pattern.route_id for c in trip)
                    and (trip[0].from_stop_id,) + tuple(c.to_stop_id for c in trip) == tuple(s.stop_id for s in pattern.stops)):
                    witnesses.append(tid)
            if not witnesses:
                raise ValueError('Scoring derivation lacks complete candidate source witness')
            witness = min(witnesses)
            retained.add(witness)
            candidate_witnesses.append({'pair_id': pair_id, 'pattern_id': pattern.pattern_id,
                                        'trip_instance_id': witness})
    for scenario in scenarios:
        for segment in scenario.segments:
            matches = [c for c in snapshot.connections if
                (c.from_stop_id, c.to_stop_id) == (segment.from_stop_id, segment.to_stop_id)
                or segment.bidirectional and (c.to_stop_id, c.from_stop_id) == (segment.from_stop_id, segment.to_stop_id)]
            if not matches:
                raise ValueError('Scoring derivation lacks declared source segment')
            if any(c.trip_instance_id in retained for c in matches):
                continue
            witness = min(matches, key=lambda c: (c.trip_instance_id, c.connection_id))
            retained.add(witness.trip_instance_id)
            scenario_witnesses.append({**segment.model_dump(mode='json'), 'trip_instance_id': witness.trip_instance_id})
    connections = tuple(c for c in snapshot.connections if c.trip_instance_id in retained)
    scored = snapshot.__class__.model_validate(snapshot.model_copy(update={'connections': connections}).model_dump(mode='json'))
    proof = {'version': SCORING_VERSION, 'cutoff_s': cutoff,
        'full_snapshot_sha256': digest(snapshot), 'scoring_snapshot_sha256': digest(scored),
        'full_connection_count': len(snapshot.connections), 'scoring_connection_count': len(connections),
        'retained_trip_ids': sorted(retained), 'retained_trip_ids_sha256': digest(sorted(retained)),
        'candidate_source_witnesses': candidate_witnesses, 'scenario_segment_witnesses': scenario_witnesses}
    return scored, proof


def cap(route):
    return min(route.duration_s, 5400) if route.duration_s is not None else 5400


def within(route):
    return route.duration_s is not None and route.duration_s <= 3600


def query_rows(baseline, disrupted, recovered, cohort, closure_end):
    if not (len(baseline) == len(disrupted) == len(recovered)):
        raise ValueError('Paired route lengths differ')
    result = []
    for b, d, r in zip(baseline, disrupted, recovered):
        if not (b.request == d.request == r.request):
            raise ValueError('Paired request identities differ')
        result.append({**b.request.model_dump(mode='json'),
            'baseline_duration_s': b.duration_s, 'disrupted_duration_s': d.duration_s,
            'recovered_duration_s': r.duration_s, 'baseline_capped_duration_s': cap(b),
            'disrupted_capped_duration_s': cap(d), 'recovered_capped_duration_s': cap(r),
            'baseline_within60': within(b), 'disrupted_within60': within(d),
            'recovered_within60': within(r), 'nominal_impacted': b.request.request_id in cohort,
            'saved_capped_duration_s': cap(d) - cap(r),
            'improved': cap(r) < cap(d),
            'recovered_arrival_after_closure': r.arrival_s is not None and r.arrival_s > closure_end})
    return result


def metrics(rows, used):
    lost = sum(r['baseline_within60'] and not r['disrupted_within60'] for r in rows)
    restored = sum(r['baseline_within60'] and not r['disrupted_within60'] and r['recovered_within60'] for r in rows)
    saved = sum(r['saved_capped_duration_s'] for r in rows)
    return {'request_count': len(rows),
        'baseline_within60_count': sum(r['baseline_within60'] for r in rows),
        'disrupted_within60_count': sum(r['disrupted_within60'] for r in rows),
        'recovered_within60_count': sum(r['recovered_within60'] for r in rows),
        'lost_count': lost, 'restored_count': restored,
        'restored_fraction': restored / lost if lost else None,
        'baseline_total_capped_duration_s': sum(r['baseline_capped_duration_s'] for r in rows),
        'disrupted_total_capped_duration_s': sum(r['disrupted_capped_duration_s'] for r in rows),
        'total_capped_duration_s': sum(r['recovered_capped_duration_s'] for r in rows),
        'added_capped_duration_s': sum(r['disrupted_capped_duration_s'] - r['baseline_capped_duration_s'] for r in rows),
        'saved_capped_duration_s': saved, 'improved_count': sum(r['improved'] for r in rows),
        'used_bus_hours': used, 'saved_query_minutes_per_bus_hour': saved / 60 / used if used else None,
        'decomposition': {name: {'count': len(selected),
            'saved_capped_duration_s': sum(r['saved_capped_duration_s'] for r in selected),
            'improved_count': sum(r['improved'] for r in selected)} for name, selected in (
                ('nominal_impacted', [r for r in rows if r['nominal_impacted']]),
                ('not_nominal_impacted', [r for r in rows if not r['nominal_impacted']]),
                ('arrival_after_closure', [r for r in rows if r['recovered_arrival_after_closure']]),
                ('arrival_by_closure_or_unavailable', [r for r in rows if not r['recovered_arrival_after_closure']]))}}


def frequency_ranking(snapshot, candidates, start, end):
    trips = defaultdict(list)
    for c in snapshot.connections:
        trips[c.trip_instance_id].append(c)
    pairs = {p.pair_id: p for p in snapshot.recovery_pairs}
    result = []
    for pair_id in sorted({c.pair_id for c in candidates}):
        pair = pairs[pair_id]
        supported = set()
        for pattern in (pair.outbound, pair.inbound):
            for tid in pattern.source_trip_instance_ids:
                trip = sorted(trips.get(tid, ()), key=lambda c: c.sequence)
                if (trip and all(c.mode == 'bus' and c.route_id == pattern.route_id for c in trip)
                    and (trip[0].from_stop_id,) + tuple(c.to_stop_id for c in trip) == tuple(s.stop_id for s in pattern.stops)
                    and start <= trip[0].departure_s < end):
                    supported.add(tid)
        result.append({'pair_id': pair_id, 'source_trip_count': len(supported),
                       'source_trip_ids': sorted(supported)})
    return sorted(result, key=lambda x: (-x['source_trip_count'], x['pair_id']))


class _IsolatedArchive:
    """Builder writes caches only in a fresh study workspace; originals read by source archive."""
    def __init__(self, archive, root):
        self.archive, self.root = archive, Path(root)
        (self.root / 'runtime').mkdir(parents=True, exist_ok=True)

    def latest(self, *args, **kwargs):
        return self.archive.latest(*args, **kwargs)

    def read(self, receipt):
        return self.archive.read(receipt)


def prepare(archive, output, config_path=CONFIG, dates=None):
    from .snapshots import build_snapshot
    config = read_config(config_path)
    output = Path(output)
    network = None
    pilot_path = None
    if config.get('network_config'):
        from .case_network import materialize_pilot
        spec = ROOT / config['network_config']
        pilot_path = output / 'network/pilot.json'
        materialized = materialize_pilot(spec, pilot_path, base_pilot_path=ROOT / 'configs/pilot.json')
        if materialized['pilot_sha256'] != sha(pilot_path.read_bytes()):
            raise ValueError('Materialized source pilot hash differs')
        if materialized['network_config_sha256'] != sha(spec.read_bytes()):
            raise ValueError('Materialized source network specification hash differs')
        atomic_write(output / 'network/source-audit.json', spec.read_bytes(), immutable=True)
        # Runtime absolute paths returned by adapters never enter persisted evidence.
        network = {'network_version': materialized['network_version'],
            'pilot_path': 'network/pilot.json', 'pilot_sha256': materialized['pilot_sha256'],
            'network_config_path': config['network_config'],
            'network_config_sha256': sha(spec.read_bytes()),
            'source_audit_path': 'network/source-audit.json', 'source_audit_sha256': sha(spec.read_bytes()),
            'base_pilot_sha256': sha((ROOT / 'configs/pilot.json').read_bytes())}
    # This identity exists before any selector/routing/policy calculations.
    freeze = {'config': config, 'config_sha256': sha(Path(config_path).read_bytes()),
              'config_canonical_sha256': digest(config), 'selection_version': VERSION,
              'candidate_selection_version': VERSION,
              'scoring_version': SCORING_VERSION,
              'code_sha256': code_hash(),
              'control_config_sha256': sha((ROOT / config['control_journey_set']).read_bytes())}
    if network:
        freeze['network'] = network
    write_json(output / 'protocol.json', freeze)
    all_dates = config['development_dates'] + config['confirmation_dates'] + config['replication_dates']
    reports = []
    for day in dates or all_dates:
        if day not in all_dates:
            raise ValueError('Date outside registered protocol')
        manifest_path = output / 'inputs' / f'{day}.json'
        if manifest_path.exists():
            manifest, snapshot = checked_input(output, day)
            reports.append({'date': day, 'snapshot_id': snapshot.metadata.snapshot_id, 'reused': True})
            continue
        cutoff = datetime.fromisoformat(day + 'T' + config['decision_local_time']).replace(tzinfo=ZoneInfo(config['timezone']))
        # Always fresh scratch: the unchanged builder may overwrite its own ancillary files.
        with tempfile.TemporaryDirectory(prefix='prepare-', dir=output) as scratch:
            kwargs = {'pilot_path': pilot_path.resolve()} if pilot_path else {}
            snapshot = build_snapshot(_IsolatedArchive(archive, scratch), cutoff, store=False, **kwargs)
            payload = (Path(scratch) / 'processed/snapshots' / f'{snapshot.metadata.snapshot_id}.json').read_bytes()
            quality = diagnostic_json(load_json(Path(scratch) / 'processed/snapshots' / f'{snapshot.metadata.snapshot_id}.quality.json'))
        coverage = None
        if network:
            from .case_network import snapshot_coverage
            coverage = snapshot_coverage(archive, snapshot, pilot_path.resolve(),
                                        cancelled_trip_ids=quality.get('cancelled_trip_ids', ()))
        primary, control = primary_requests(snapshot, config), control_requests(snapshot, config)
        if len(primary) != 240 or len({r.request_id for r in primary}) != 240 or len(control) != 100:
            raise ValueError('Registered primary/control census differs')
        scenario = section_scenario(snapshot, config)
        refs = [s.model_dump(mode='json') for s in snapshot.metadata.sources]
        for ref in refs:
            receipt = archive.get(ref['record_id'])
            if not receipt or datetime.fromisoformat(receipt['received_at']) > cutoff:
                raise ValueError('Source unavailable before cutoff')
            archive.read(receipt)  # verifies exact archived object content
            ref['receipt'] = receipt
        write_json(output / 'snapshots' / f'{day}.quality.json', quality)
        atomic_write(output / 'snapshots' / f'{day}.json', payload, immutable=True)
        manifest = {'date': day, 'role': next(role for role in ('development', 'confirmation', 'replication') if day in config[role + '_dates']),
            'snapshot_id': snapshot.metadata.snapshot_id, 'snapshot_sha256': sha(payload),
            'protocol_sha256': digest(freeze), 'sources': refs,
            'primary': [r.model_dump(mode='json') for r in primary],
            'controls': [r.model_dump(mode='json') for r in control],
            'scenarios': [scenario.model_dump(mode='json')],
            'primary_sha256': digest([r.model_dump(mode='json') for r in primary]),
            'control_sha256': digest([r.model_dump(mode='json') for r in control]),
            'scenario_sha256': digest([scenario.model_dump(mode='json')])}
        if network:
            manifest['network'] = network
            manifest['source_coverage'] = coverage
            manifest['source_coverage_sha256'] = digest(coverage)
        write_json(manifest_path, manifest)
        write_json(output / 'inputs' / f'{day}.sha256.json', {'sha256': digest(manifest)})
        reports.append({'date': day, 'snapshot_id': snapshot.metadata.snapshot_id, 'reused': False})
    return reports


def refreeze(output, source):
    """Carry exact prepared sources and nominal selections into a reviewed new code freeze."""
    output, source = Path(output), Path(source)
    old = load_json(source / 'protocol.json')
    protocol = {**old, 'code_sha256': code_hash(), 'scoring_version': SCORING_VERSION,
                'previous_protocol_sha256': digest(old)}
    write_json(output / 'protocol.json', protocol)
    days = []
    for path in sorted((source / 'inputs').glob('*.json')):
        if path.name.endswith('.sha256.json'):
            continue
        manifest = load_json(path)
        if digest(manifest) != load_json(path.with_suffix('.sha256.json'))['sha256']:
            raise ValueError('Prior input manifest hash mismatch')
        day = manifest['date']
        payload = (source / 'snapshots' / f'{day}.json').read_bytes()
        if sha(payload) != manifest['snapshot_sha256'] or manifest['protocol_sha256'] != digest(old):
            raise ValueError('Prior frozen source provenance mismatch')
        for name in (f'{day}.json', f'{day}.quality.json'):
            atomic_write(output / 'snapshots' / name, (source / 'snapshots' / name).read_bytes(), immutable=True)
        manifest = {**manifest, 'protocol_sha256': digest(protocol)}
        write_json(output / 'inputs' / path.name, manifest)
        write_json(output / 'inputs' / path.with_suffix('.sha256.json').name, {'sha256': digest(manifest)})
        previous_selection = source / 'selections' / path.name
        if previous_selection.exists():
            selection = load_json(previous_selection)
            if digest(selection) != load_json(previous_selection.with_suffix('.sha256.json'))['sha256']:
                raise ValueError('Prior selection hash mismatch')
            selection = {**selection, 'manifest_sha256': digest(manifest)}
            write_json(output / 'selections' / path.name, selection)
            write_json(output / 'selections' / path.with_suffix('.sha256.json').name, {'sha256': digest(selection)})
        days.append(day)
    return {'dates': days, 'code_sha256': code_hash(), 'protocol_sha256': digest(protocol),
            'previous_protocol_sha256': digest(old)}


def checked_input(output, day):
    output = Path(output)
    protocol = load_json(output / 'protocol.json')
    if protocol['code_sha256'] != code_hash():
        raise ValueError('Study code differs from frozen preparation')
    network = protocol.get('network')
    if network:
        if network['pilot_path'] != 'network/pilot.json' or network['source_audit_path'] != 'network/source-audit.json':
            raise ValueError('Nonportable network artifact reference')
        for path_key, hash_key in (('pilot_path', 'pilot_sha256'), ('source_audit_path', 'source_audit_sha256')):
            if sha((output / network[path_key]).read_bytes()) != network[hash_key]:
                raise ValueError('Frozen network artifact hash mismatch')
    manifest = load_json(output / 'inputs' / f'{day}.json')
    if digest(manifest) != load_json(output / 'inputs' / f'{day}.sha256.json')['sha256']:
        raise ValueError('Input manifest hash mismatch')
    if manifest['protocol_sha256'] != digest(protocol):
        raise ValueError('Protocol hash mismatch')
    payload = (output / 'snapshots' / f'{day}.json').read_bytes()
    if sha(payload) != manifest['snapshot_sha256']:
        raise ValueError('Snapshot hash mismatch')
    return manifest, TimetableSnapshot.model_validate_json(payload)


def select_inputs(output, day):
    output = Path(output)
    manifest, snapshot = checked_input(output, day)
    path = output / 'selections' / f'{day}.json'
    if path.exists():
        selection = load_json(path)
        if digest(selection) != load_json(path.with_suffix('.sha256.json'))['sha256'] or selection['manifest_sha256'] != digest(manifest):
            raise ValueError('Frozen selection hash mismatch')
        return selection
    config = load_json(output / 'protocol.json')['config']
    requests = tuple(JourneyRequest.model_validate(r) for r in manifest['primary'])
    scenario = CorridorClosure.model_validate(manifest['scenarios'][0])
    valid, _ = available_requests(snapshot, requests)
    nominal = generate_recovery_candidates(snapshot, valid, (scenario,), limit=config['candidate_pair_limit']) if valid else ()
    candidates = tuple(RecoveryCandidate(candidate_id=f'{c.candidate_id}:phase:{offset}',
        pair_id=c.pair_id, activation_s=snapshot.metadata.snapshot_s + offset)
        for c in nominal for offset in config['activation_offsets_seconds'])
    baseline = routes(snapshot, requests)
    disrupted = routes(apply_scenarios(snapshot, (scenario,)).snapshot, requests)
    cohort = sorted(b.request.request_id for b, d in zip(baseline, disrupted)
                    if b.reachable and cap(d) > cap(b))
    selection = {'manifest_sha256': digest(manifest), 'selection_version': VERSION,
        'candidate_selection_version': VERSION,
        'candidates': [c.model_dump(mode='json') for c in candidates],
        'candidate_sha256': digest([c.model_dump(mode='json') for c in candidates]),
        'nominal_impacted_request_ids': cohort,
        'frequency_ranking': frequency_ranking(snapshot, candidates, scenario.start_s, scenario.end_s)}
    write_json(path, selection)
    write_json(path.with_suffix('.sha256.json'), {'sha256': digest(selection)})
    return selection


def simple_ids(search, ranking):
    reasons = []
    for ranked in ranking:
        candidates = sorted((c for c in search.candidates.values() if c.pair_id == ranked['pair_id']),
                            key=lambda c: (c.activation_s, c.candidate_id))
        feasible = [c.candidate_id for c in candidates if c.candidate_id in search.feasible]
        if feasible:
            return tuple(feasible[:search.max_buses]), reasons
        reasons.append({'pair_id': ranked['pair_id'], 'reason': 'No complete feasible duty',
                        'candidate_issues': [x.model_dump(mode='json') for x in search.infeasible_reasons if x.candidate_id in {c.candidate_id for c in candidates}]})
    return (), reasons


def compute_cell(output, day, budget, delta):
    """Independently evaluate simple plan, and include it among the best evaluated alternatives."""
    from .analysis import plan_with_unavailable
    output = Path(output)
    manifest, nominal = checked_input(output, day)
    selection = select_inputs(output, day)
    config = load_json(output / 'protocol.json')['config']
    snapshot, transform = stress_snapshot(nominal, delta)
    requests = tuple(JourneyRequest.model_validate(r) for r in manifest['primary'])
    controls = tuple(JourneyRequest.model_validate(r) for r in manifest['controls'])
    candidates = tuple(RecoveryCandidate.model_validate(c) for c in selection['candidates'])
    scenarios = tuple(CorridorClosure.model_validate(s) for s in manifest['scenarios'])
    scored, scoring = scoring_snapshot(snapshot, requests, scenarios, candidates)
    valid, _ = available_requests(scored, requests)
    search = _Search(scored, valid, scenarios, candidates, budget) if valid else None
    simple, reasons = simple_ids(search, selection['frequency_ranking']) if search else ((), [])
    result = plan_with_unavailable(scored, requests, scenarios, candidates, budget,
                                  max_swap_evaluations=config['max_swap_evaluations'])
    plans = {'no_action': (), 'simple_frequency': simple, 'best_evaluated': result.plan.candidate_ids}
    if search:
        plans['best_evaluated'] = min((search.evaluate(simple), search.evaluate(result.plan.candidate_ids), search.evaluate(())), key=_plan_key).candidate_ids
    baseline, disrupted_snapshot = routes(snapshot, requests), apply_scenarios(snapshot, scenarios).snapshot
    disrupted = routes(disrupted_snapshot, requests)
    control_baseline, control_disrupted = routes(snapshot, controls), routes(disrupted_snapshot, controls)
    cohort = set(selection['nominal_impacted_request_ids'])
    policies = {}
    for name, ids in plans.items():
        additions = tuple(c for cid in ids for c in search.additions[cid]) if ids else ()
        extended = snapshot.model_copy(update={'connections': snapshot.connections + additions})
        final = apply_scenarios(extended, scenarios).snapshot
        recovered = routes(final, requests) if ids else disrupted
        control_recovered = routes(final, controls) if ids else control_disrupted
        rows = query_rows(baseline, disrupted, recovered, cohort, scenarios[0].end_s)
        control_rows = query_rows(control_baseline, control_disrupted, control_recovered, set(), scenarios[0].end_s)
        policies[name] = {'candidate_ids': list(ids), 'duties': [search.duties[c].model_dump(mode='json') for c in ids] if ids else [],
            'full': metrics(rows, len(ids) * 2),
            'impacted': metrics([r for r in rows if r['nominal_impacted']], len(ids) * 2),
            'controls': metrics(control_rows, len(ids) * 2),
            'queries': rows, 'control_queries': control_rows,
            'baseline_routes': [r.model_dump(mode='json') for r in baseline],
            'disrupted_routes': [r.model_dump(mode='json') for r in disrupted],
            'recovered_routes': [r.model_dump(mode='json') for r in recovered],
            'control_baseline_routes': [r.model_dump(mode='json') for r in control_baseline],
            'control_disrupted_routes': [r.model_dump(mode='json') for r in control_disrupted],
            'control_recovered_routes': [r.model_dump(mode='json') for r in control_recovered]}
        # Fail closed if scoring derivation ever changes the actual full objective.
        if search:
            objective = search.evaluate(ids).objective
            full = policies[name]['full']
            missing_count = len(requests) - len(valid)
            if (objective.restored_count, objective.total_capped_duration_s + missing_count * 5400, objective.bus_hours) != (full['restored_count'], full['total_capped_duration_s'], full['used_bus_hours']):
                raise ValueError('Scoring and full published objective differ')
            policies[name]['scoring_objective'] = {'restored_count': objective.restored_count,
                'total_capped_duration_s': objective.total_capped_duration_s + missing_count * 5400,
                'bus_hours': objective.bus_hours}
    return {'date': day, 'budget_bus_hours': budget, 'additional_bus_seconds': delta,
        'manifest_sha256': digest(manifest), 'selection_sha256': digest(selection),
        'code_sha256': code_hash(), 'candidate_selection_version': VERSION,
        'network_config_sha256': manifest.get('network', {}).get('network_config_sha256'),
        'source_coverage_sha256': manifest.get('source_coverage_sha256'),
        'input_sha256': digest({'manifest_sha256': digest(manifest), 'selection_sha256': digest(selection),
                               'budget_bus_hours': budget, 'additional_bus_seconds': delta,
                               'derived_snapshot_sha256': digest(snapshot), 'scoring_sha256': digest(scoring),
                               'code_sha256': code_hash()}),
        'derived_snapshot_sha256': digest(snapshot),
        'scoring': scoring,
        'transform': transform, 'policies': policies, 'simple_policy_rejections': reasons,
        'infeasible_candidates': [x.model_dump(mode='json') for x in search.infeasible_reasons] if search else [],
        'search_evaluated_plan_count': result.evaluated_plan_count,
        'comparison_evaluated_plan_count': len(search.cache) if search else 1,
        'best_evaluated_scope': 'Best lexicographic objective among unchanged bounded search, independently scored simple frequency plan and no action',
        'optimality_proven': False}


def cell_path(output, day, budget, delta):
    return Path(output) / 'cells' / f'{day}-b{budget}-d{delta}.json'


def checked_cell(output, day, budget, delta):
    manifest, _ = checked_input(output, day)
    selection = select_inputs(output, day)
    path = cell_path(output, day, budget, delta)
    doc = load_json(path)
    if sha(path.read_bytes()) != load_json(path.with_suffix('.sha256.json'))['sha256']:
        raise ValueError('Cell result hash mismatch')
    if doc['result']['manifest_sha256'] != digest(manifest) or doc['result']['selection_sha256'] != digest(selection) or doc['result']['code_sha256'] != code_hash():
        raise ValueError('Cell provenance mismatch')
    if (doc['result']['date'], doc['result']['budget_bus_hours'], doc['result']['additional_bus_seconds']) != (day, budget, delta):
        raise ValueError('Cell identity differs from filename')
    return doc


def run_date(output, day, *, allow_registered=False, cells=None, on_progress=None):
    output = Path(output)
    config = load_json(output / 'protocol.json')['config']
    if day not in config['development_dates'] and not allow_registered:
        raise ValueError('Confirmation/replication require explicit coordinator authorization')
    matrix = [(b, 0) for b in config['budgets_bus_hours']] + [(config['sensitivity_budget_bus_hours'], d) for d in config['sensitivity_seconds'] if d]
    reports = []
    for budget, delta in cells or matrix:
        if (budget, delta) not in matrix:
            raise ValueError('Cell outside registered resource matrix')
        path = cell_path(output, day, budget, delta)
        if path.exists():
            saved = checked_cell(output, day, budget, delta)
            reused = True
        else:
            started = time.perf_counter()
            result = compute_cell(output, day, budget, delta)
            saved = {'result': result, 'calculation_elapsed_seconds': time.perf_counter() - started}
            write_json(path, saved)
            write_json(path.with_suffix('.sha256.json'), {'sha256': sha(path.read_bytes())})
            reused = False
        row = {'date': day, 'budget': budget, 'delta': delta, 'reused': reused,
               'elapsed_seconds': saved['calculation_elapsed_seconds'],
               'metrics': saved['result']['policies']['best_evaluated']['full']}
        reports.append(row)
        if on_progress:
            on_progress(row)
    return reports


def compact_budget(cell, snapshot):
    result = cell['result']
    policy = result['policies']['best_evaluated']
    m = policy['full']
    example = next(r for r in policy['queries'] if r['origin_stop_id'] == '600194' and r['destination_stop_id'] == '600018' and r['departure_s'] == snapshot.metadata.snapshot_s)
    fields = ('restored_count', 'recovered_within60_count', 'saved_capped_duration_s', 'improved_count', 'saved_query_minutes_per_bus_hour')
    return {'budget_bus_hours': result['budget_bus_hours'], 'used_bus_hours': m['used_bus_hours'],
        'bus_count': len(policy['candidate_ids']), **{k: m[k] for k in fields},
        'run_id': f"{result['date']}-b{result['budget_bus_hours']}-d{result['additional_bus_seconds']}",
        'policies': {name: {k: p['full'][k] for k in ('restored_count', 'total_capped_duration_s', 'used_bus_hours')} for name, p in result['policies'].items()},
        'example': {**{k: example[k] for k in ('request_id', 'departure_s', 'baseline_duration_s', 'disrupted_duration_s', 'recovered_duration_s')},
                    'origin_name': 'Fairfield platform 2', 'destination_name': 'Central platform 1'}}


def report(output, *, include_development=False):
    output = Path(output)
    protocol = load_json(output / 'protocol.json')
    config = protocol['config']
    dates, complete = [], []
    for day in config['development_dates'] + config['confirmation_dates'] + config['replication_dates']:
        if day in config['development_dates'] and not include_development:
            continue
        if not cell_path(output, day, 0, 0).exists():
            continue
        manifest, snapshot = checked_input(output, day)
        selection = select_inputs(output, day)
        cells = [checked_cell(output, day, b, d) for b, d in [(b, 0) for b in config['budgets_bus_hours']] + [(2, d) for d in (300, 600)]]
        nominal = cells[0]['result']['policies']['no_action']['full']
        dates.append({'date': day, 'role': manifest['role'], 'snapshot_id': snapshot.metadata.snapshot_id,
            'snapshot_at': snapshot.metadata.snapshot_at.isoformat(),
            **{k: nominal[k] for k in ('request_count', 'baseline_within60_count', 'disrupted_within60_count', 'lost_count', 'added_capped_duration_s')},
            'impacted_count': len(selection['nominal_impacted_request_ids']),
            'budgets': [compact_budget(c, snapshot) for c in cells[:4]],
            'sensitivities': [{**compact_budget(c, snapshot), 'additional_bus_seconds': c['result']['additional_bus_seconds']} for c in [cells[1], *cells[4:]]],
            'example': None})
        complete.extend({'run_id': f"{day}-b{c['result']['budget_bus_hours']}-d{c['result']['additional_bus_seconds']}",
            **{k: v for k, v in c['result'].items() if k != 'policies'},
            'calculation_elapsed_seconds': c['calculation_elapsed_seconds'],
            'policies': {name: {k: v for k, v in p.items() if not k.endswith('_routes')}
                         for name, p in c['result']['policies'].items()}} for c in cells)
    study = {'schema_version': 1, 'study_id': config['study_id'], 'title': 'Broad rail outage: fixed platform journey census',
        'question': 'How do hypothetical bus duties change the fixed journey workload under a two-hour rail outage?',
        'disruption': 'Hypothetical Fairfield–Central rail outage; conservative whole-trip cancellation',
        'classification': 'Derived scenario outputs; recorded predictions and schedule fallback are not observed arrivals',
        'protocol': {'version': VERSION, 'hash': digest(protocol), 'config_sha256': protocol['config_sha256'],
                     'selection_rule': config['primary_selection_rule'], 'reachability_seconds': 3600, 'duration_cap_seconds': 5400},
        'assumptions': [config['interpretation'], config['duty_horizon_limit'], 'Incomplete real walking access; fixed primary and separate control denominators; bounded search conditional on supplied candidates.'],
        'dates': dates, 'evidence': [{'label': 'Machine-readable metrics and paired query rows', 'url': 'https://suhail15.github.io/brisbane-transport-resilience-lab/data/case-study-metrics.json'}, {'label': 'Protocol and source provenance', 'url': 'https://suhail15.github.io/brisbane-transport-resilience-lab/data/case-study-evidence.json'}]}
    atomic_write(output / 'case-study.json', canonical(study))
    atomic_write(output / 'case-study-metrics.json', canonical(complete))
    atomic_write(output / 'case-study-evidence.json', canonical({'protocol': protocol, 'inputs': [load_json(output / 'inputs' / f"{d['date']}.json") for d in dates], 'quality': {d['date']: load_json(output / 'snapshots' / f"{d['date']}.quality.json") for d in dates}}))
    return {'dates': [d['date'] for d in dates], 'cells': len(complete), 'output': str(output / 'case-study.json')}


def pack(output, destination, dates):
    output, destination = Path(output), Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use a fresh reproduction directory')
    files = ['protocol.json']
    protocol = load_json(output / 'protocol.json')
    if protocol.get('network'):
        files += ['network/pilot.json', 'network/source-audit.json']
    for day in dates:
        checked_input(output, day)
        files += [f'inputs/{day}.json', f'inputs/{day}.sha256.json', f'snapshots/{day}.json', f'snapshots/{day}.quality.json', f'selections/{day}.json', f'selections/{day}.sha256.json']
        for b, d in [(b, 0) for b in (0, 2, 4, 8)] + [(2, 300), (2, 600)]:
            checked_cell(output, day, b, d)
            p = cell_path(output, day, b, d)
            files += [p.relative_to(output).as_posix(), p.with_suffix('.sha256.json').relative_to(output).as_posix()]
    for relative in files:
        atomic_write(destination / 'study' / relative, (output / relative).read_bytes(), immutable=True)
    config_name = {'corridor-impact-v1': 'corridor-impact.v1.json',
                   'corridor-impact-v2': 'corridor-impact.v2.json'}[protocol['config'].get('study_id', 'corridor-impact-v2')]
    for path in code_files() + [ROOT / 'requirements.lock.txt', ROOT / 'configs' / config_name, ROOT / 'configs/journey-set.v1.json', ROOT / 'LICENSE', ROOT / 'DATA_LICENSE.md']:
        atomic_write(destination / 'code' / path.relative_to(ROOT), path.read_bytes(), immutable=True)
    atomic_write(destination / 'README.txt', 'Private preparation; publication requires source/licence review. Normalized snapshots include Translink schedule data (CC BY 4.0 conditions) and OSM-derived walking links (ODbL 1.0, OpenStreetMap contributors). No raw archive originals are included. Install code/requirements.lock.txt, then run python code/scripts/run_case_study.py reproduce --destination . --expected-manifest-sha256 REVIEWED_HASH from this directory. Verify the externally reviewed manifest hash.\n', immutable=True)
    manifest = {'schema_version': 1, 'dates': dates, 'code_sha256': code_hash(),
        'files': {p.relative_to(destination).as_posix(): sha(p.read_bytes()) for p in sorted(destination.rglob('*')) if p.is_file()}}
    write_json(destination / 'manifest.json', manifest)
    return {'manifest_sha256': digest(manifest), 'files': len(manifest['files'])}


def reproduce(destination, expected_manifest_sha256=None, on_progress=None):
    destination = Path(destination)
    manifest_bytes = (destination / 'manifest.json').read_bytes()
    if expected_manifest_sha256 and sha(manifest_bytes) != expected_manifest_sha256:
        raise ValueError('Reviewed reproduction manifest hash mismatch')
    manifest = json.loads(manifest_bytes)
    verify_manifest_files(destination, manifest['files'])
    if manifest['code_sha256'] != code_hash():
        raise ValueError('Matching frozen study code required')
    results = []
    for day in manifest['dates']:
        for budget, delta in [(b, 0) for b in (0, 2, 4, 8)] + [(2, 300), (2, 600)]:
            saved = checked_cell(destination / 'study', day, budget, delta)['result']
            actual = compute_cell(destination / 'study', day, budget, delta)
            if saved != actual:
                raise ValueError(f'Exact study recomputation mismatch: {day}/{budget}/{delta}')
            row = {'date': day, 'budget': budget, 'delta': delta, 'matched': True}
            results.append(row)
            if on_progress:
                on_progress(row)
    return results
