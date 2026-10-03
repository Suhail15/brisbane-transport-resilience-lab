"""Frozen source-selected pilot pairs; dates never silently change the denominator."""
import json
from pathlib import Path
from ..contracts import JourneyRequest

PATH=Path('configs/journey-set.v1.json')

def expand(snapshot,start_s=None):
    config=json.loads(PATH.read_text());start=snapshot.metadata.snapshot_s if start_s is None else start_s
    return tuple(JourneyRequest(request_id=f"{config['version']}:{pair['pair_id']}:{offset}",origin_stop_id=pair['origin_stop_id'],destination_stop_id=pair['destination_stop_id'],departure_s=start+offset) for pair in config['pairs'] for offset in (0,900,1800,2700,3600))
