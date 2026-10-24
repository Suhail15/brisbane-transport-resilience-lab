"""Reject mismatched approval evidence before a public directory is created."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
DATES = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22']


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize('corruption,message', [
    ('partial', 'protocol-matched complete 24-cell'),
    ('different_protocol', 'protocol-matched complete 24-cell'),
    ('missing_cell', 'cell identities differ'),
    ('changed_cell', 'checked cell bytes differ'),
    ('duplicate_reproduction', 'reproduction cell identities differ'),
    ('unmatched_reproduction', 'reproduction cell identities differ'),
])
def test_export_rejects_wrong_or_incomplete_evidence(tmp_path, corruption, message):
    study = tmp_path / 'study'
    write(study / 'protocol.json', {'study_id': 'synthetic-guard-fixture'})
    protocol_sha = hashlib.sha256((study / 'protocol.json').read_bytes()).hexdigest()
    verified_cells, reproduced_cells = {}, []
    for day in DATES:
        for budget, delta in [(b, 0) for b in (0, 2, 4, 8)] + [(2, 300), (2, 600)]:
            key = f'{day}-b{budget}-d{delta}'
            path = study / 'cells' / (key + '.json')
            write(path, {'synthetic_cell_identity': key})
            verified_cells[key] = {'passed': True, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            reproduced_cells.append({'date': day, 'budget': budget, 'delta': delta, 'matched': True})
    verification = {'passed': True, 'status': 'complete', 'verified_cell_count': 24,
                    'dates': DATES, 'protocol_sha256': protocol_sha, 'cells': verified_cells,
                    'errors': [], 'missing_cells': []}
    reproduction = {'passed': True, 'verified_cell_count': 24, 'dates': DATES,
                    'protocol_sha256': protocol_sha, 'cells': reproduced_cells}
    if corruption == 'partial':
        verification['verified_cell_count'] = 23
    elif corruption == 'different_protocol':
        reproduction['protocol_sha256'] = '0' * 64
    elif corruption == 'missing_cell':
        verified_cells.pop(next(iter(verified_cells)))
    elif corruption == 'changed_cell':
        write(study / 'cells' / (next(iter(verified_cells)) + '.json'), {'changed': True})
    elif corruption == 'duplicate_reproduction':
        reproduced_cells[-1] = reproduced_cells[0]
    else:
        reproduced_cells[-1]['matched'] = False
    verification_path, reproduction_path = tmp_path / 'verification.json', tmp_path / 'reproduction.json'
    write(verification_path, verification)
    write(reproduction_path, reproduction)
    output = tmp_path / 'public'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_case_study_bundle.py'),
        '--study', str(study), '--output', str(output), '--verification', str(verification_path),
        '--reproduction', str(reproduction_path), '--report', str(tmp_path / 'report.json')],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode != 0
    assert message in result.stderr
    assert not output.exists()
