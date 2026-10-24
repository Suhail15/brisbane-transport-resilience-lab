"""Manual arithmetic and immutable/offline checks; synthetic fixtures only."""
import json
from itertools import combinations

import pytest

from resilience.contracts import CorridorClosure, CorridorSegment, RecoveryCandidate, RouteResult
from resilience.engine.recovery import _Search, _plan_key
from resilience.pipeline import case_study as cs
from tests.engine.fixtures import connection, paired_pattern, request, snapshot, walk


def fixture_study(root, network=None):
    pair, sources = paired_pattern('p', 'C', 'D')
    sources = tuple(c.model_copy(update={'departure_s': c.departure_s + 20000,
                                        'arrival_s': c.arrival_s + 20000}) for c in sources)
    data = snapshot((connection('rail', 'A', 'B', 0, 600, mode='rail'),) + sources,
                    walks=(walk('A', 'C'), walk('D', 'B')), pairs=(pair,))
    primary = (request('A', 'B'), request('absent', 'B', request_id='missing'))
    controls = (request('C', 'D', request_id='control'),)
    scenario = CorridorClosure(scenario_id='rail-only', start_s=0, end_s=7200,
                              segments=(CorridorSegment(from_stop_id='A', to_stop_id='B'),))
    config = {'development_dates': ['2026-10-02'], 'budgets_bus_hours': [0, 2, 4, 8],
              'sensitivity_budget_bus_hours': 2, 'sensitivity_seconds': [0, 300, 600],
              'candidate_pair_limit': 3, 'activation_offsets_seconds': [600, 1500, 2400, 3300],
              'max_swap_evaluations': 128}
    protocol = {'config': config, 'code_sha256': cs.code_hash()}
    if network:
        protocol['network'] = network
    cs.write_json(root / 'protocol.json', protocol)
    payload = data.model_dump_json().encode()
    cs.atomic_write(root / 'snapshots/2026-10-02.json', payload, immutable=True)
    cs.write_json(root / 'snapshots/2026-10-02.quality.json', {})
    manifest = {'date': '2026-10-02', 'snapshot_id': data.metadata.snapshot_id,
                'snapshot_sha256': cs.sha(payload), 'protocol_sha256': cs.digest(protocol),
                'primary': [r.model_dump(mode='json') for r in primary],
                'controls': [r.model_dump(mode='json') for r in controls],
                'scenarios': [scenario.model_dump(mode='json')]}
    cs.write_json(root / 'inputs/2026-10-02.json', manifest)
    cs.write_json(root / 'inputs/2026-10-02.sha256.json', {'sha256': cs.digest(manifest)})
    return data


def test_fixed_census_has_240_distinct_queries_and_separate_original_controls():
    config = cs.read_config()
    data = snapshot()
    requests = cs.primary_requests(data, config)
    controls = cs.control_requests(data, config)
    assert len(requests) == len({r.request_id for r in requests}) == 240
    assert len({(r.origin_stop_id, r.destination_stop_id) for r in requests}) == 48
    assert len(controls) == len({r.request_id for r in controls}) == 100
    assert not {r.request_id for r in requests} & {r.request_id for r in controls}
    original = cs.read_config(cs.ROOT / 'configs/corridor-impact.v1.json')
    assert cs.primary_requests(data, original) == requests
    assert cs.control_requests(data, original) == controls


def test_undefined_walking_diagnostics_are_explicit_nulls():
    projected = cs.diagnostic_json({'paths': [{'distance': float('inf')}], 'valid': 3})
    assert projected['paths'][0]['distance'] is None
    assert projected['undefined_diagnostic_values']['paths'] == ['/paths/0/distance']
    assert projected['valid'] == 3
    cs.canonical(projected)


def test_source_closure_keeps_directed_rail_segments_and_rejects_bus_cancellation():
    data = snapshot((connection('out', 'A', 'B', 0, 600, mode='rail'),
                     connection('back', 'B', 'A', 1000, 1600, mode='rail')))
    names = {'A': 'Fairfield station, platform 1', 'B': 'Central station, platform 1'}
    data = data.model_copy(update={'stops': tuple(s.model_copy(update={'name': names[s.stop_id]}) for s in data.stops)})
    config = {'section_station_names': ['Fairfield', 'Central'], 'closure_duration_seconds': 7200}
    scenario = cs.section_scenario(data, config)
    assert {(s.from_stop_id, s.to_stop_id) for s in scenario.segments} == {('A', 'B'), ('B', 'A')}
    assert all(not s.bidirectional for s in scenario.segments)
    bad = data.model_copy(update={'connections': data.connections + (connection('bus', 'A', 'B', 0, 600),)})
    with pytest.raises(ValueError, match='rail-only'):
        cs.section_scenario(bad, config)


def test_manual_signed_metrics_caps_nulls_cohort_and_postclosure():
    data = snapshot(stops=('A', 'B'))
    def route(i, duration):
        return RouteResult(request=request('A', 'B', request_id=i), quality=data.metadata.quality,
                           reachable=duration is not None, duration_s=duration,
                           arrival_s=duration)
    before = tuple(route(str(i), d) for i, d in enumerate((600, None, 6000, 1000)))
    disrupted = tuple(route(str(i), d) for i, d in enumerate((None, None, 8000, 900)))
    recovered = tuple(route(str(i), d) for i, d in enumerate((1200, None, 6000, 800)))
    rows = cs.query_rows(before, disrupted, recovered, {'0'}, 1000)
    m = cs.metrics(rows, 2)
    assert m['request_count'] == 4 and m['lost_count'] == m['restored_count'] == 1
    assert m['saved_capped_duration_s'] == 4300 and m['improved_count'] == 2
    assert m['added_capped_duration_s'] == 4700
    assert m['saved_query_minutes_per_bus_hour'] == 4300 / 120
    assert m['decomposition']['nominal_impacted']['saved_capped_duration_s'] == 4200
    assert m['decomposition']['arrival_after_closure']['saved_capped_duration_s'] == 4200
    assert cs.metrics(rows, 0)['saved_query_minutes_per_bus_hour'] is None
    empty = cs.metrics([], 0)
    assert empty['restored_fraction'] is None and empty['request_count'] == 0


def test_source_frequency_counts_unique_full_trips_and_freezes_order():
    pair, sources = paired_pattern('p', 'A', 'B')
    data = snapshot(sources, pairs=(pair,))
    candidates = (RecoveryCandidate(candidate_id='a', pair_id='p', activation_s=600),
                  RecoveryCandidate(candidate_id='b', pair_id='p', activation_s=1500))
    ranking = cs.frequency_ranking(data, candidates, 0, 2000)
    assert ranking == [{'pair_id': 'p', 'source_trip_count': 1, 'source_trip_ids': ['p:source:out']}]
    search = _Search(data, (request('A', 'B'),), (), candidates, 4)
    assert cs.simple_ids(search, ranking) == (('a', 'b'), [])


def test_actual_simple_plan_manual_benefit_control_and_immutable_resume(tmp_path):
    fixture_study(tmp_path)
    cell = cs.compute_cell(tmp_path, '2026-10-02', 2, 0)
    simple = cell['policies']['simple_frequency']
    # Walk100, board at600, bus600, walk100 =>1300; disruption capped5400.
    assert simple['full']['saved_capped_duration_s'] == 4100
    assert simple['full']['restored_count'] == 1
    assert simple['full']['request_count'] == 2
    assert simple['impacted']['request_count'] == 1
    assert simple['controls']['request_count'] == 1
    assert simple['control_queries'][0]['recovered_duration_s'] == 1200
    assert cell['policies']['no_action']['candidate_ids'] == []
    assert cell['candidate_selection_version'] == cs.VERSION
    first = cs.run_date(tmp_path, '2026-10-02', cells=[(2, 0)])
    path = cs.cell_path(tmp_path, '2026-10-02', 2, 0)
    contents = path.read_bytes()
    second = cs.run_date(tmp_path, '2026-10-02', cells=[(2, 0)])
    assert not first[0]['reused'] and second[0]['reused'] and path.read_bytes() == contents
    doc = json.loads(contents)
    doc['result']['policies']['simple_frequency']['full']['saved_capped_duration_s'] += 1
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='Cell result hash'):
        cs.run_date(tmp_path, '2026-10-02', cells=[(2, 0)])


def test_tampered_input_and_changed_protocol_fail_closed(tmp_path):
    fixture_study(tmp_path)
    path = tmp_path / 'snapshots/2026-10-02.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='Snapshot hash'):
        cs.checked_input(tmp_path, '2026-10-02')
    with pytest.raises(ValueError, match='authorization'):
        cs.run_date(tmp_path, '2026-10-22')
    with pytest.raises(ValueError, match='immutable file collision'):
        cs.write_json(tmp_path / 'protocol.json', {'changed': True})


def test_complete_offline_pack_recomputes_and_detects_tampering(tmp_path):
    study, dest = tmp_path / 'study', tmp_path / 'offline'
    fixture_study(study)
    cs.run_date(study, '2026-10-02')
    packed = cs.pack(study, dest, ['2026-10-02'])
    manifest = cs.load_json(dest / 'manifest.json')
    for relative in ('services/resilience/pipeline/case_network.py',
                     'services/resilience/pipeline/snapshots.py',
                     'services/resilience/pipeline/schedule.py',
                     'services/resilience/pipeline/walking.py',
                     'services/resilience/pipeline/archive.py',
                     'configs/station-access-network.v1.json', 'configs/pilot.json'):
        assert 'code/' + relative in manifest['files']
    assert len(cs.reproduce(dest, packed['manifest_sha256'])) == 6
    assert not list(dest.rglob('*.zip'))
    path = dest / 'study/snapshots/2026-10-02.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='hash mismatch'):
        cs.reproduce(dest, packed['manifest_sha256'])


def test_whole_trip_scoring_matches_every_small_plan_and_retains_witnesses(tmp_path):
    data = fixture_study(tmp_path)
    late = connection('late-unrelated', 'A', 'Z', 50000, 50600)
    witness = connection('late-segment', 'E', 'F', 51000, 51600, mode='rail')
    # A trip that begins before cutoff retains its complete later suffix.
    long = (connection('whole', 'G', 'H', 1, 2),
            connection('whole', 'H', 'I', 49000, 50000, sequence=1))
    data = snapshot(data.connections + (late, witness) + long,
                    walks=data.walking_links, pairs=data.recovery_pairs)
    requests = (request('A', 'B'), request('A', 'Z', request_id='late-query'))
    scenario = CorridorClosure(scenario_id='rail', start_s=0, end_s=7200,
        segments=(CorridorSegment(from_stop_id='A', to_stop_id='B'),
                  CorridorSegment(from_stop_id='E', to_stop_id='F')))
    candidates = tuple(RecoveryCandidate(candidate_id=f'p:{offset}', pair_id='p', activation_s=offset)
                       for offset in (600, 1500, 2400, 3300))
    scored, proof = cs.scoring_snapshot(data, requests, (scenario,), candidates)
    assert proof['cutoff_s'] == 5400
    assert 'late-unrelated' not in proof['retained_trip_ids']
    assert 'late-segment' in proof['retained_trip_ids']
    assert {c.sequence for c in scored.connections if c.trip_instance_id == 'whole'} == {0, 1}
    assert len(proof['candidate_source_witnesses']) == 2
    assert proof['scenario_segment_witnesses'] == [{'from_stop_id': 'E', 'to_stop_id': 'F',
                                                  'bidirectional': True, 'trip_instance_id': 'late-segment'}]
    for delta in (0, 300, 600):
        full, _ = cs.stress_snapshot(data, delta)
        bounded, _ = cs.scoring_snapshot(full, requests, (scenario,), candidates)
        full_search = _Search(full, requests, (scenario,), candidates, 8)
        bounded_search = _Search(bounded, requests, (scenario,), candidates, 8)
        for count in range(5):
            for ids in combinations(tuple(c.candidate_id for c in candidates), count):
                assert _plan_key(full_search.evaluate(ids)) == _plan_key(bounded_search.evaluate(ids))
        assert full_search.baseline[1].duration_s == 50600 + delta
        assert bounded_search.baseline[1].duration_s is None


def test_full_route_cache_binds_changed_requests_and_snapshot():
    data = snapshot((connection('bus', 'A', 'B', 10, 20),))
    early = (request('A', 'B'),)
    late = (request('A', 'B', departure=11),)
    assert cs.routes(data, early)[0].duration_s == 20
    assert cs.routes(data, late)[0].duration_s is None
    changed = data.model_copy(update={'connections': ()})
    assert cs.routes(changed, early)[0].duration_s is None


def test_portable_network_artifacts_are_bound_and_tampering_fails(tmp_path):
    pilot, audit = b'{"fixture":"pilot"}', b'{"fixture":"source audit"}'
    cs.atomic_write(tmp_path / 'network/pilot.json', pilot, immutable=True)
    cs.atomic_write(tmp_path / 'network/source-audit.json', audit, immutable=True)
    network = {'pilot_path': 'network/pilot.json', 'pilot_sha256': cs.sha(pilot),
               'source_audit_path': 'network/source-audit.json', 'source_audit_sha256': cs.sha(audit)}
    fixture_study(tmp_path, network)
    cs.checked_input(tmp_path, '2026-10-02')
    (tmp_path / 'network/pilot.json').write_bytes(pilot + b' ')
    with pytest.raises(ValueError, match='network artifact hash'):
        cs.checked_input(tmp_path, '2026-10-02')


def test_machine_specific_network_paths_are_rejected(tmp_path):
    fixture_study(tmp_path, {'pilot_path': '/machine-specific/pilot.json',
                            'source_audit_path': 'network/source-audit.json'})
    with pytest.raises(ValueError, match='Nonportable network'):
        cs.checked_input(tmp_path, '2026-10-02')
