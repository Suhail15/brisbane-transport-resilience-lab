"""Report fixed morning cells from immutable saved results; never rerun policies."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configs/morning-evaluation.v1.json'
DATES = ('2026-10-19', '2026-10-20', '2026-10-21')
SCENARIOS = ('cancellation', 'stop_closure', 'rail_corridor', 'bus_delay')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def expected_cells(config):
    if tuple(config['evaluation_dates']) != DATES or tuple(config['scenarios']) != SCENARIOS:
        raise ValueError('fixed final dates/scenarios changed')
    if config['budgets_bus_hours'] != [0, 2, 4, 8] or config['sensitivity_seconds'] != [0, 300, 600]:
        raise ValueError('fixed budget/sensitivity matrix changed')
    for day in DATES:
        for scenario in SCENARIOS:
            for budget, delta in [(b, 0) for b in config['budgets_bus_hours']] + (
                    [(2, 300), (2, 600)] if scenario == 'stop_closure' else []):
                yield f'{day}.{scenario}.b{budget}.s{delta}', day, scenario, budget, delta


def within(route):
    return bool(route['reachable'] and route['duration_s'] is not None and route['duration_s'] <= 3600)


def capped(route):
    return min(route['duration_s'], 5400) if route['duration_s'] is not None else 5400


def objective_key(value):
    return (-value['restored_count'], value['total_capped_duration_s'], value['bus_hours'])


def comparison(chosen, other):
    if other is None:
        return None
    a, b = objective_key(chosen), objective_key(other)
    return 'better' if a < b else 'equal_objective_components' if a == b else 'worse'


def verify_result(evaluation_root, key, row, cell, target):
    _, day, scenario, budget, delta = cell
    run_id = row['run_id']
    if not isinstance(run_id, str) or not run_id.isalnum():
        raise ValueError(f'{key}: unsafe run ID')
    run = read(evaluation_root / 'results' / f'{key}.json')
    processed = evaluation_root.parent
    final = read(processed / 'run-results' / f'{run_id}.json')
    if run != final or run.get('run_id') != run_id or run.get('status') != 'completed' or not run.get('result'):
        raise ValueError(f'{key}: morning result is not the authoritative immutable completed run')
    inp_path = processed / 'run-inputs' / f'{run_id}.input.json'
    inp_bytes = inp_path.read_bytes(); inp = json.loads(inp_bytes)
    meta = read(processed / 'run-inputs' / f'{run_id}.metadata.json')
    if inp_bytes != canonical(inp) or inp != run.get('input') or meta != run.get('metadata'):
        raise ValueError(f'{key}: immutable input/metadata differs from result')
    for field in ('snapshot_id', 'snapshot_content_sha256', 'budget_bus_hours', 'max_swap_evaluations',
                  'assumptions', 'source_record_ids', 'engine_code_sha256', 'journey_set_version'):
        if inp.get(field) != meta.get(field):
            raise ValueError(f'{key}: immutable input/metadata {field} differs')
    sha = digest(inp)
    if sha != meta['input_sha256'] or sha != row['input_sha256']:
        raise ValueError(f'{key}: input SHA256 differs')
    for field, collection in [('request_set_sha256', 'requests'), ('scenario_set_sha256', 'scenarios'), ('candidate_set_sha256', 'candidates')]:
        if meta[field] != digest(inp[collection]):
            raise ValueError(f'{key}: {collection} identity differs')
    if (row['date'], row['scenario'], row['budget_bus_hours'], row['sensitivity_seconds']) != (day, scenario, budget, delta):
        raise ValueError(f'{key}: summary cell identity differs')
    if (inp['snapshot_id'] != target['snapshot_id'] or inp['requests'] != target['requests']
            or inp['scenarios'] != [target['scenarios'][scenario]] or inp['budget_bus_hours'] != budget
            or inp['assumptions']['bus_running_time_sensitivity_seconds'] != delta
            or inp['max_swap_evaluations'] != 128
            or inp['snapshot_content_sha256'] != target['snapshot_content_sha256']):
        raise ValueError(f'{key}: result differs from frozen target/matrix')
    evaluation = run['result']['plan']['evaluation']; metrics = evaluation['metrics']
    if row['metrics'] != metrics or row['objective'] != run['result']['plan']['objective']:
        raise ValueError(f'{key}: summary measures differ from immutable result')
    if len(inp['requests']) != 100 or any(r.get('od_weight') is not None for r in inp['requests']):
        raise ValueError(f'{key}: fixed equal-weight request denominator differs')
    ids = [r['request_id'] for r in inp['requests']]
    sets = {}
    for label in ('baseline', 'disrupted', 'recovered'):
        routes = evaluation[label]
        if [r['request']['request_id'] for r in routes] != ids or [r['request'] for r in routes] != inp['requests']:
            raise ValueError(f'{key}: {label} route denominator/order differs')
        sets[label] = {r['request']['request_id'] for r in routes if within(r)}
        if metrics[label + '_reachable_count'] != len(sets[label]) or metrics[label + '_total_capped_duration_s'] != sum(capped(r) for r in routes):
            raise ValueError(f'{key}: {label} saved metrics differ from route arithmetic')
    lost = sets['baseline'] - sets['disrupted']; restored = lost & sets['recovered']
    if (metrics['request_count'] != 100 or metrics['lost_count'] != len(lost)
            or metrics['restored_count'] != len(restored) or metrics['restored_fraction'] != (len(restored)/len(lost) if lost else None)
            or metrics['reachability_horizon_s'] != 3600 or metrics['duration_cap_s'] != 5400):
        raise ValueError(f'{key}: saved reachability/lost/restored/cap arithmetic differs')
    plan = run['result']['plan']
    if plan['bus_hours'] > budget or plan['objective'] != {'restored_count': len(restored),
            'total_capped_duration_s': metrics['recovered_total_capped_duration_s'], 'bus_hours': plan['bus_hours']}:
        raise ValueError(f'{key}: chosen objective or resource accounting differs')
    if run['result']['no_intervention'] != {'restored_count': 0,
            'total_capped_duration_s': metrics['disrupted_total_capped_duration_s'], 'bus_hours': 0}:
        raise ValueError(f'{key}: no-action objective differs from disrupted routes')
    return run


def summarize(summary_path, config, allow_partial=False):
    evaluation_root = Path(summary_path).resolve().parent
    summary = read(summary_path); cells = list(expected_cells(config))
    expected_keys = {c[0] for c in cells}
    if set(summary) - expected_keys:
        raise ValueError('summary includes unplanned cells; no date/scenario substitution is allowed')
    missing = [key for key, *_ in cells if key not in summary or summary[key].get('status') != 'completed']
    if missing and not allow_partial:
        raise ValueError(f'final report requires all 54 completed cells; missing/incomplete {len(missing)}: {", ".join(missing)}')
    plan = read(evaluation_root / 'plan.json')
    if (plan['config'] != config or plan['config_sha256'] != digest(config)
            or plan['plan_sha256'] != digest(plan['plan'])):
        raise ValueError('current config differs from immutable prepared plan')
    targets = {day: read(evaluation_root / 'targets' / f'{day}.json') for day in DATES}
    signatures = []
    for day, target in targets.items():
        if (target['date'] != day or target['status'] != 'prepared' or target['config_sha256'] != digest(config)
                or target['plan_sha256'] != plan['plan_sha256']
                or target['snapshot_id'] != plan['plan']['decision_snapshots'][day]
                or target['request_set_sha256'] != digest(target['requests'])):
            raise ValueError(f'{day}: target not fixed/prepared under this config')
        signatures.append([(r['request_id'], r['origin_stop_id'], r['destination_stop_id'], r['departure_s']) for r in target['requests']])
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise ValueError('request OD/departure identities differ across fixed dates')
    records, origins, rejections, runtime = [], [], [], []
    candidate_hashes = {}
    for cell in cells:
        key, day, scenario, budget, delta = cell
        if key in missing:
            continue
        run = verify_result(evaluation_root, key, summary[key], cell, targets[day])
        result = run['result']; chosen = result['plan']; ev = chosen['evaluation']; metrics = ev['metrics']
        pair_key = day, scenario
        candidates = run['metadata']['candidate_set_sha256']
        if pair_key in candidate_hashes and candidate_hashes[pair_key] != candidates:
            raise ValueError(f'{key}: nominal/sensitivity candidate identities differ')
        candidate_hashes[pair_key] = candidates
        record = {'key': key, 'date': day, 'scenario': scenario, 'budget_bus_hours': budget,
                  'sensitivity_seconds': delta, 'run_id': run['run_id'], 'input_sha256': run['metadata']['input_sha256'],
                  'snapshot_id': run['snapshot_id'], **metrics, 'selected_bus_hours': chosen['bus_hours'],
                  'selected_candidate_ids': chosen['candidate_ids'], 'candidate_count': len(result['considered_candidate_ids']),
                  'infeasible_candidate_count': len(result['infeasible_candidates']), 'evaluated_plan_count': result['evaluated_plan_count'],
                  'selected_objective': chosen['objective'], 'no_action_objective': result['no_intervention'],
                  'simple_policy_objective': result['busiest_affected_pattern'],
                  'versus_no_action': comparison(chosen['objective'], result['no_intervention']),
                  'versus_simple_policy': comparison(chosen['objective'], result['busiest_affected_pattern']),
                  'duration_reduction_vs_no_action_s': metrics['disrupted_total_capped_duration_s'] - metrics['recovered_total_capped_duration_s'],
                  'optimality_proven': result['optimality_proven'], 'method': result['method'], 'tie_break': result['tie_break'],
                  'immutable_result_path': str(evaluation_root / 'results' / f'{key}.json')}
        records.append(record)
        for issue in result['infeasible_candidates']:
            rejections.append({'key': key, 'run_id': run['run_id'], **issue})
        runtime.append({'key': key, 'run_id': run['run_id'], 'created_at': run.get('created_at'),
            'started_at': run.get('started_at'), 'completed_at': run.get('completed_at'),
            'elapsed_seconds': run.get('elapsed_seconds'),
            'timing_scope': 'saved elapsed field; no derived duration from created_at alone' if run.get('elapsed_seconds') is not None else 'not recorded'})
        grouped = defaultdict(lambda: defaultdict(int))
        for b, d, r in zip(ev['baseline'], ev['disrupted'], ev['recovered']):
            aggregate = grouped[b['request']['origin_stop_id']]
            aggregate['request_count'] += 1
            aggregate['baseline_within_60m'] += within(b); aggregate['disrupted_within_60m'] += within(d); aggregate['recovered_within_60m'] += within(r)
            aggregate['lost_count'] += within(b) and not within(d)
            aggregate['restored_count'] += within(b) and not within(d) and within(r)
            aggregate['disruption_capped_delta_s'] += capped(d)-capped(b)
            aggregate['recovery_capped_reduction_s'] += capped(d)-capped(r)
        origins.extend({'key': key, 'date': day, 'scenario': scenario, 'budget_bus_hours': budget,
                        'sensitivity_seconds': delta, 'origin_stop_id': origin, **values}
                       for origin, values in sorted(grouped.items()))
    ranked = defaultdict(lambda: defaultdict(int))
    for row in origins:
        # Compare the twelve nominal no-action scenario/date cells once, avoiding duplication across policy budgets.
        if row['budget_bus_hours'] != 0 or row['sensitivity_seconds'] != 0:
            continue
        aggregate = ranked[row['origin_stop_id']]
        aggregate['scenario_date_cells'] += 1
        for field in ('request_count', 'lost_count', 'disruption_capped_delta_s'):
            aggregate[field] += row[field]
    ranking = sorted((dict(origin_stop_id=origin, **values) for origin, values in ranked.items()),
                     key=lambda r: (-r['lost_count'], -r['disruption_capped_delta_s'], r['origin_stop_id']))
    return {'version': config['version'], 'complete': not missing, 'expected_cells': 54,
            'completed_cells': len(records), 'missing_or_incomplete_cells': missing, 'dates': list(DATES),
            'config_sha256': digest(config), 'records': records, 'origin_impacts': origins,
            'ranked_origins_nominal_no_action': ranking, 'candidate_rejections': rejections, 'runtime_evidence': runtime,
            'verification_scope': 'Immutable result/input/metadata identities, frozen target payloads and saved route arithmetic; independent source/archive verification is a separate release check; no route or optimization recomputation.'}


def csv_text(rows):
    if not rows:
        return ''
    fields = list(dict.fromkeys(key for row in rows for key in row))
    buffer = io.StringIO(newline=''); writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: 'null' if value is None else json.dumps(value, sort_keys=True, separators=(',', ':')) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return buffer.getvalue()


def markdown(report, output_dir):
    lines = ['# Final recorded-morning evaluation' if report['complete'] else '# PARTIAL recorded-morning evaluation — not final findings', '',
        f"Completed fixed cells: **{report['completed_cells']}/54**. Dates: 19, 20 and 21 October 2026; source cutoff 07:30:05 Australia/Brisbane.", '',
        'The same 100 equal-weight planned requests (20 fixed OD pairs × five departures) are retained in every cell, including absent stops and unreachable outcomes. They are queries, not observed demand or passenger counts. Recorded feed predictions and scheduled fallbacks are not measured arrivals. Disruptions, planned connection misses and relief bus duties are hypothetical. OSM walking coverage remains incomplete.', '',
        'B/D/R counts mean baseline/disrupted/recovered journeys within 60 minutes. Capped totals sum min(duration, 5,400 seconds), with 5,400 seconds for an unavailable duration, across all 100 requests; null restored fractions remain null when nothing was lost. Positive duration reduction is across fixed queries and does not estimate passenger savings. Negative disruption deltas can occur when hypothetical changed timings create different feasible planned connections; they are retained.', '',
        'All four scenarios and budgets 0/2/4/8 are shown. Stop closure budget two adds +300/+600-second running-time stresses to its reused nominal zero level. Candidate identities are paired. Search is bounded to twelve candidates and 128 swap evaluations; global optimality is not proven. Extra fleet availability is unverified.', '',
        f"Config SHA256: `{report['config_sha256']}`. {report['verification_scope']}", '',
        '| Date | Scenario | Budget | Stress,s | B/D/R ≤60m | Lost/restored | Restored fraction | Capped B/D/R,s | Used bus-hours | Reduction vs no action,s | Run |',
        '|---|---|---:|---:|---|---|---|---|---:|---:|---|']
    for row in report['records']:
        link = Path(os.path.relpath(row['immutable_result_path'], output_dir)).as_posix()
        counts = '/'.join(str(row[k + '_reachable_count']) for k in ('baseline','disrupted','recovered'))
        totals = '/'.join(str(row[k + '_total_capped_duration_s']) for k in ('baseline','disrupted','recovered'))
        fraction = 'null' if row['restored_fraction'] is None else str(row['restored_fraction'])
        lines.append(f"|{row['date']}|{row['scenario']}|{row['budget_bus_hours']}|{row['sensitivity_seconds']}|{counts}|{row['lost_count']}/{row['restored_count']}|{fraction}|{totals}|{row['selected_bus_hours']}|{row['duration_reduction_vs_no_action_s']}|[{row['run_id']}]({link})|")
    lines += ['', '## Policy objectives and provenance', '',
        'Objectives are (restored requests, total capped seconds, bus-hours): maximize the first, then minimize the second and third. Equal objective components do not establish the final sorted-candidate-ID tie-break against a simple policy whose selected IDs are not separately saved. A null simple policy means unavailable/inapplicable, not a zero-performance claim.', '',
        '| Run | Input SHA256 | Chosen objective | No action | Simple busiest affected service pattern | Chosen vs simple |',
        '|---|---|---|---|---|---|']
    def obj(value):
        return 'null' if value is None else f"({value['restored_count']}, {value['total_capped_duration_s']}, {value['bus_hours']})"
    for row in report['records']:
        link = Path(os.path.relpath(row['immutable_result_path'], output_dir)).as_posix()
        lines.append(f"|[{row['run_id']}]({link})|`{row['input_sha256']}`|{obj(row['selected_objective'])}|{obj(row['no_action_objective'])}|{obj(row['simple_policy_objective'])}|{row['versus_simple_policy'] or 'null'}|")
    lines += ['', '## Origin impacts', '',
        'Ranking uses only the twelve nominal no-action scenario/date cells, counted once each. The same requests recur across scenarios/dates; these sums are repeated query exposures, not distinct people. Sort: lost requests, then signed disruption capped-duration increase. Every origin/cell is retained in origin-impacts.csv.', '',
        '| Origin stop | Available scenario/date cells | Query exposures | Lost | Signed capped increase,s |', '|---|---:|---:|---:|---:|']
    for row in report['ranked_origins_nominal_no_action']:
        lines.append(f"|{row['origin_stop_id']}|{row['scenario_date_cells']}|{row['request_count']}|{row['lost_count']}|{row['disruption_capped_delta_s']}|")
    lines += ['', '## Candidate feasibility and runtime', '',
        f"Saved rejected candidate records: {len(report['candidate_rejections'])}; see candidate-rejections.csv/report.json for exact IDs and reasons. Runtime is separate in runtime.csv; missing elapsed/start/completion fields remain null. A creation timestamp alone cannot identify execution duration, queue delay or end-to-end latency.", '',
        'Missed connection counts refer to simulated planned transfers under the fixed model; they are not observed missed boardings. No broad performance, global optimality or actual fleet feasibility claim follows from this report.', '',
        'The historical afternoon development findings are preserved separately in docs/DEVELOPMENT_FINDINGS.md. Development and reserve dates do not replace a final cell. Public release depends on the independently reviewed release gates.', '']
    if report['missing_or_incomplete_cells']:
        lines += ['## Missing or incomplete cells', '', *['- `' + key + '`' for key in report['missing_or_incomplete_cells']], '']
    return '\n'.join(lines)


def write_report(report, output_dir):
    output_dir = Path(output_dir).resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    files = {'report.json': json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n',
             'metrics.csv': csv_text(report['records']), 'origin-impacts.csv': csv_text(report['origin_impacts']),
             'candidate-rejections.csv': csv_text(report['candidate_rejections']), 'runtime.csv': csv_text(report['runtime_evidence']),
             'report.md': markdown(report, output_dir)}
    for name, content in files.items():
        destination = output_dir / name; temporary = destination.with_suffix(destination.suffix + '.tmp')
        temporary.write_text(content, encoding='utf-8', newline='\n'); temporary.replace(destination)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, default=ROOT / 'data/processed/morning-evaluation-v1/summary.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/processed/morning-evaluation-v1/report')
    parser.add_argument('--allow-partial', action='store_true', help='Explicitly label incomplete output; never use as final findings')
    args = parser.parse_args()
    try:
        report = summarize(args.summary, read(CONFIG), args.allow_partial)
        write_report(report, args.output_dir)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f'Report refused: {exc}\n')
    print(json.dumps({'complete': report['complete'], 'completed_cells': report['completed_cells'], 'expected_cells': 54, 'output_dir': str(args.output_dir)}))


if __name__ == '__main__':
    main()
