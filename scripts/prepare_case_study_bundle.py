"""Add the reviewed case study without replacing the original demo comparisons."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil

def read(path):
    return json.loads(Path(path).read_bytes())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n')

p = argparse.ArgumentParser()
p.add_argument('--base', type=Path, default=Path('data/derived/morning-public-v1'))
p.add_argument('--study', type=Path, default=Path('data/processed/corridor-impact-v2'))
p.add_argument('--output', type=Path, required=True)
p.add_argument('--verification', type=Path, required=True)
p.add_argument('--reproduction', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
args = p.parse_args()
verification, reproduction = read(args.verification), read(args.reproduction)
expected_dates = {'2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22'}
protocol_sha = sha(args.study / 'protocol.json')
for report in (verification, reproduction):
    if (report.get('passed') is not True or report.get('verified_cell_count') != 24
            or set(report.get('dates', [])) != expected_dates
            or report.get('protocol_sha256') != protocol_sha):
        raise SystemExit('Public projection requires protocol-matched complete 24-cell verification and reproduction')
if verification.get('status') != 'complete' or verification.get('errors') or verification.get('missing_cells'):
    raise SystemExit('Independent verification is incomplete')
expected_cells = {f'{day}-b{b}-d{d}' for day in expected_dates
                  for b, d in [(b, 0) for b in (0, 2, 4, 8)] + [(2, 300), (2, 600)]}
if set(verification.get('cells', {})) != expected_cells:
    raise SystemExit('Independent verification cell identities differ')
for name, cell in verification['cells'].items():
    if cell.get('passed') is not True or cell.get('sha256') != sha(args.study / 'cells' / (name + '.json')):
        raise SystemExit('Independently checked cell bytes differ: ' + name)
reproduced = reproduction.get('cells', [])
if (len(reproduced) != 24 or any(r.get('matched') is not True for r in reproduced)
        or {f"{r['date']}-b{r['budget']}-d{r['delta']}" for r in reproduced} != expected_cells):
    raise SystemExit('Exact reproduction cell identities differ')
if args.output.exists():
    raise SystemExit('Use a fresh public projection directory')
base_manifest = read(args.base / 'manifest.json')
for rel, expected in base_manifest['files'].items():
    if sha(args.base / rel) != expected:
        raise SystemExit('Original public file hash mismatch: ' + rel)
study = read(args.study / 'case-study.json')
if study.get('protocol', {}).get('hash') != protocol_sha:
    raise SystemExit('Compact study protocol identity differs')
study.update(title='When the Fairfield–Central rail corridor closes',
    question='How much can extra buses help, and how many bus-hours do they use?',
    disruption='Hypothetically close the Fairfield–Central rail section from 07:30 to 09:30. Every train crossing the section during that interval is cancelled for its complete trip in this model.',
    classification='Recorded inputs · hypothetical closure and extra buses')
base_url = 'https://suhail15.github.io/brisbane-transport-resilience-lab/'
study['evidence'] = [
    {'label': 'All policy metrics and resource assumptions', 'url': base_url + 'case-study-metrics.json'},
    {'label': 'Per-query primary and separate control results (CSV)', 'url': base_url + 'case-study-queries.csv'},
    {'label': 'Frozen protocol, source coverage and verification identities', 'url': base_url + 'case-study-evidence.json'},
    {'label': 'Study findings and interpretation', 'url': 'https://github.com/Suhail15/brisbane-transport-resilience-lab/blob/main/docs/CORRIDOR_CASE_STUDY.md'},
]
if {d['date'] for d in study['dates']} != expected_dates:
    raise SystemExit('Study must retain all registered public dates')
shutil.copytree(args.base, args.output)
metrics, sources, rows = [], [], []
policy_labels = {'no_action': 'No extra service', 'simple_frequency': 'Most frequent relevant bus pattern', 'best_evaluated': 'Best evaluated recovery'}
for date in study['dates']:
    day = date['date']
    manifest = read(args.study / 'inputs' / f'{day}.json')
    selection = read(args.study / 'selections' / f'{day}.json')
    snapshot = read(args.study / 'snapshots' / f'{day}.json')
    nominal = read(args.study / 'cells' / f'{day}-b0-d0.json')['result']['policies']['no_action']['full']
    for field in ('request_count', 'baseline_within60_count', 'disrupted_within60_count', 'lost_count', 'added_capped_duration_s'):
        if date.get(field) != nominal[field]:
            raise SystemExit('Compact date metric differs: ' + day + '/' + field)
    if (date.get('role') != manifest['role'] or date.get('snapshot_id') != manifest['snapshot_id']
            or date.get('impacted_count') != len(selection['nominal_impacted_request_ids'])
            or {b['budget_bus_hours'] for b in date['budgets']} != {0, 2, 4, 8}
            or len(date['budgets']) != 4
            or {(b['budget_bus_hours'], b['additional_bus_seconds']) for b in date['sensitivities']} != {(2, 0), (2, 300), (2, 600)}
            or len(date['sensitivities']) != 3):
        raise SystemExit('Compact date source or comparison identities differ: ' + day)
    for item in date['budgets'] + date['sensitivities']:
        delta = item.get('additional_bus_seconds', 0)
        result = read(args.study / 'cells' / f"{day}-b{item['budget_bus_hours']}-d{delta}.json")['result']
        best = result['policies']['best_evaluated']
        for field in ('used_bus_hours', 'restored_count', 'recovered_within60_count', 'saved_capped_duration_s', 'improved_count', 'saved_query_minutes_per_bus_hour'):
            if item.get(field) != best['full'][field]:
                raise SystemExit('Compact budget metric differs: ' + day + '/' + field)
        if item.get('bus_count') != len(best['candidate_ids']) or set(item['policies']) != set(result['policies']):
            raise SystemExit('Compact plan or policy identities differ: ' + day)
        for name, policy in item['policies'].items():
            for field in ('restored_count', 'total_capped_duration_s', 'used_bus_hours'):
                if policy.get(field) != result['policies'][name]['full'][field]:
                    raise SystemExit('Compact policy metric differs: ' + day + '/' + name + '/' + field)
        example = next(r for r in best['queries'] if r['origin_stop_id'] == '600194'
                       and r['destination_stop_id'] == '600018' and r['departure_s'] == manifest['primary'][0]['departure_s'])
        for field in ('request_id', 'departure_s', 'baseline_duration_s', 'disrupted_duration_s', 'recovered_duration_s'):
            if item.get('example', {}).get(field) != example[field]:
                raise SystemExit('Compact fixed example differs: ' + day + '/' + field)
        decomposition = result['policies']['best_evaluated']['full']['decomposition']
        item.update(impacted_saved_capped_duration_s=decomposition['nominal_impacted']['saved_capped_duration_s'],
                    other_saved_capped_duration_s=decomposition['not_nominal_impacted']['saved_capped_duration_s'],
                    after_closure_saved_capped_duration_s=decomposition['arrival_after_closure']['saved_capped_duration_s'])
        for name, policy in item['policies'].items():
            policy['name'] = policy_labels[name]
    for budget, delta in [(b, 0) for b in (0, 2, 4, 8)] + [(2, 300), (2, 600)]:
        path = args.study / 'cells' / f'{day}-b{budget}-d{delta}.json'
        cell = read(path)
        result = cell['result']
        summary = {k: v for k, v in result.items() if k != 'policies'}
        summary['cell_sha256'] = sha(path)
        summary['calculation_elapsed_seconds'] = cell['calculation_elapsed_seconds']
        summary['policies'] = {}
        for name, policy in result['policies'].items():
            summary['policies'][name] = {k: v for k, v in policy.items() if not k.endswith('_routes') and k not in ('queries', 'control_queries')}
            for cohort, key in [('primary', 'queries'), ('controls', 'control_queries')]:
                rows.extend({'date': day, 'budget_bus_hours': budget, 'additional_bus_seconds': delta,
                             'policy': name, 'cohort': cohort, **r} for r in policy[key])
        metrics.append(summary)
    walking_rel = f'walking/corridor-{day}.json'
    write(args.output / walking_rel, {'licence': 'ODbL 1.0', 'licence_url': 'https://opendatacommons.org/licenses/odbl/1-0/',
        'attribution': '© OpenStreetMap contributors', 'source_osm_sha256': next(s['sha256'] for s in manifest['sources'] if s['source_kind'] == 'osm'),
        'walking_links': snapshot['walking_links']})
    sources.append({**{k: manifest[k] for k in ('date', 'role', 'snapshot_id', 'snapshot_sha256', 'protocol_sha256', 'primary_sha256', 'control_sha256', 'scenarios', 'network', 'source_coverage', 'source_coverage_sha256')},
        'sources': [{k: ref[k] for k in ('record_id', 'source_kind', 'received_at', 'event_at', 'sha256')} for ref in manifest['sources']],
        'selection': selection, 'quality': snapshot['metadata']['quality'], 'walking_database_url': walking_rel})
write(args.output / 'case-study.json', study)
write(args.output / 'case-study-metrics.json', {'schema_version': 1, 'cells': metrics})
write(args.output / 'case-study-evidence.json', {'protocol': read(args.study / 'protocol.json'), 'inputs': sources,
    'independent_verification_sha256': sha(args.verification), 'reproduction_report_sha256': sha(args.reproduction),
    'limits': 'Normalized input reproduction and model accounting; not observed passenger outcomes or globally optimal dispatch.'})
buffer = io.StringIO(newline='')
writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
writer.writeheader()
writer.writerows(rows)
(args.output / 'case-study-queries.csv').write_text(buffer.getvalue(), newline='')
catalog = read(args.output / 'catalog.json')
catalog['case_study_url'] = 'case-study.json'
write(args.output / 'catalog.json', catalog)
manifest = {k: v for k, v in base_manifest.items() if k != 'files'}
manifest['extensions'] = [{'study_id': study['study_id'], 'protocol_sha256': study['protocol']['hash']}]
manifest['files'] = {f.relative_to(args.output).as_posix(): sha(f) for f in sorted(args.output.rglob('*')) if f.is_file() and f.name != 'manifest.json'}
write(args.output / 'manifest.json', manifest)
unchanged = [rel for rel, expected in base_manifest['files'].items() if rel != 'catalog.json' and sha(args.output / rel) == expected]
assert len(unchanged) == len(base_manifest['files']) - 1
write(args.report, {'passed': True, 'original_files_unchanged': len(unchanged),
    'dates': sorted(expected_dates), 'cells': len(metrics), 'query_rows': len(rows), 'public_manifest_sha256': sha(args.output / 'manifest.json'),
    'scope': 'Original result/replay/input/licence files preserved byte-for-byte; catalog adds one reference. New compact summaries, query CSV and ODbL walking databases are separately reviewed.'})
print(json.dumps({'passed': True, 'cells': len(metrics), 'query_rows': len(rows), 'manifest': sha(args.output / 'manifest.json')}))
