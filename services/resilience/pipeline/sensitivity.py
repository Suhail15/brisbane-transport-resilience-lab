"""Approved hypothetical bus running-time stress; actual rail/OSM are unchanged."""
from collections import defaultdict
from math import ceil
from ..contracts import PatternPair

VERSION='bus-running-time-proportional-v1'

def stress_snapshot(snapshot,delta):
    if delta not in (0,300,600):raise ValueError('stress must be 0,300,600 seconds')
    if not delta:return snapshot,{'method':VERSION,'delta_seconds':0,'unsupported_trip_ids':[]}
    trips=defaultdict(list);unsupported=[];changed=[]
    for c in snapshot.connections:trips[c.trip_instance_id].append(c)
    for tid,connections in trips.items():
        ordered=sorted(connections,key=lambda c:c.sequence)
        if ordered[0].mode!='bus':changed.extend(ordered);continue
        duration=ordered[-1].arrival_s-ordered[0].departure_s
        future=next((c for c in ordered if c.departure_s>=snapshot.metadata.snapshot_s),None)
        if duration<=0:unsupported.append(tid);changed.extend(ordered);continue
        if not future:changed.extend(ordered);continue
        anchor=future.departure_s
        scale=lambda value:(value*(duration+delta)+duration-1)//duration
        for c in ordered:
            if c.sequence<future.sequence:changed.append(c)
            else:changed.append(c.model_copy(update={'departure_s':anchor+scale(c.departure_s-anchor),'arrival_s':anchor+scale(c.arrival_s-anchor)}))
    pairs=[]
    for pair in snapshot.recovery_pairs:
        directions=[]
        for pattern in (pair.outbound,pair.inbound):
            duration=pattern.stops[-1].arrival_offset_s
            scale=lambda value:(value*(duration+delta)+duration-1)//duration
            directions.append(pattern.model_copy(update={'stops':tuple(s.model_copy(update={'arrival_offset_s':scale(s.arrival_offset_s),'departure_offset_s':scale(s.departure_offset_s)}) for s in pattern.stops)}))
        pairs.append(PatternPair(pair_id=pair.pair_id,outbound=directions[0],inbound=directions[1]))
    derived=snapshot.__class__.model_validate(snapshot.model_copy(update={'connections':tuple(changed),'recovery_pairs':tuple(pairs)}).model_dump(mode='json'))
    return derived,{'method':VERSION,'delta_seconds':delta,'nominal_snapshot_id':snapshot.metadata.snapshot_id,'unsupported_trip_ids':unsupported,'classification':'hypothetical running-time sensitivity; not observed delay'}
