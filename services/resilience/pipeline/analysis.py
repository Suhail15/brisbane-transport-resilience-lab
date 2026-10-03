"""Versioned analysis inputs and explicit unavailable-request outcomes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ..contracts import (AnalysisAssumptions,RunMetadata,RouteResult,RecoveryObjective,
    RecoveryResult,RecoveryPlan,ScenarioEvaluation,EvaluationMetrics)
from ..engine import ENGINE_VERSION,JOURNEY_SET_VERSION,OBJECTIVE_VERSION,plan_recovery,apply_scenarios
from .files import atomic_write

ROOT=Path(__file__).resolve().parents[3]

def canonical(value):
    if hasattr(value,'model_dump'):value=value.model_dump(mode='json')
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def engine_digest():
    paths=[ROOT/'services/resilience/contracts.py',*sorted((ROOT/'services/resilience/engine').glob('*.py'))]
    content=b''.join(p.relative_to(ROOT).as_posix().encode()+b'\0'+p.read_bytes()+b'\0' for p in paths)
    return hashlib.sha256(content).hexdigest()

def prepare_input(archive,snapshot,requests,scenarios,candidates,budget,*,journey_set_version=JOURNEY_SET_VERSION,delta=0,derived=None,max_swaps=128):
    path=archive.root/'processed'/'snapshots'/f'{snapshot.metadata.snapshot_id}.json'
    snapshot_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    assumptions=AnalysisAssumptions(bus_running_time_sensitivity_seconds=delta)
    sources=snapshot.metadata.sources
    source_ids=tuple(sorted(s.record_id for s in sources))
    gtfs=next(s.sha256 for s in sources if s.source_kind=='gtfs')
    osm=next((s.sha256 for s in sources if s.source_kind=='osm'),None)
    adapter_hash=hashlib.sha256(b''.join(p.read_bytes() for p in (Path(__file__),Path(__file__).with_name('sensitivity.py'),Path(__file__).with_name('journey_set.py')))).hexdigest()
    normalized={'adapter_code_sha256':adapter_hash,'schema_version':1,'engine_version':ENGINE_VERSION,'engine_code_sha256':engine_digest(),'journey_set_version':journey_set_version,'snapshot_id':snapshot.metadata.snapshot_id,'snapshot_at':snapshot.metadata.snapshot_at.isoformat(),'snapshot_content_sha256':snapshot_hash,'source_gtfs_sha256':gtfs,'source_osm_sha256':osm,'source_record_ids':list(source_ids),'requests':[r.model_dump(mode='json') for r in requests],'scenarios':[s.model_dump(mode='json') for s in scenarios],'candidates':[c.model_dump(mode='json') for c in candidates],'budget_bus_hours':budget,'search_method':'greedy_bounded_swap','objective_version':OBJECTIVE_VERSION,'candidate_selection_version':'affected-corridor-topology-v1','max_swap_evaluations':max_swaps,'assumptions':assumptions.model_dump(mode='json'),'derived_input':derived}
    metadata=RunMetadata(input_sha256=digest(normalized),engine_version=ENGINE_VERSION,engine_code_sha256=normalized['engine_code_sha256'],journey_set_version=journey_set_version,request_set_sha256=digest(normalized['requests']),scenario_set_sha256=digest(normalized['scenarios']),candidate_set_sha256=digest(normalized['candidates']),budget_bus_hours=budget,snapshot_id=snapshot.metadata.snapshot_id,snapshot_at=snapshot.metadata.snapshot_at,snapshot_content_sha256=snapshot_hash,source_gtfs_sha256=gtfs,source_osm_sha256=osm,source_record_ids=source_ids,objective_version=OBJECTIVE_VERSION,max_swap_evaluations=max_swaps,assumptions=assumptions)
    return normalized,metadata

def persist_input(archive,run_id,normalized,metadata):
    root=archive.root/'processed'/'run-inputs'
    atomic_write(root/f'{run_id}.input.json',canonical(normalized),immutable=True)
    atomic_write(root/f'{run_id}.metadata.json',canonical(metadata),immutable=True)

def available_requests(snapshot,requests):
    ids={s.stop_id for s in snapshot.stops}
    return tuple(r for r in requests if r.origin_stop_id in ids and r.destination_stop_id in ids),tuple(r for r in requests if r.origin_stop_id not in ids or r.destination_stop_id not in ids)

def plan_with_unavailable(snapshot,requests,scenarios,candidates,budget,**kwargs):
    valid,missing=available_requests(snapshot,requests)
    unavailable=tuple(RouteResult(request=r,reachable=False,quality=snapshot.metadata.quality.model_copy(update={'warnings':snapshot.metadata.quality.warnings+('Adapter unavailable: source stop id absent in this snapshot; retained in request denominator',)})) for r in missing)
    if valid:
        result=plan_recovery(snapshot,valid,scenarios,candidates,budget,**kwargs)
        if not missing:return result
        ev=result.plan.evaluation;metrics=ev.metrics.model_copy(update={'request_count':len(requests),**{key:getattr(ev.metrics,key)+5400*len(missing) for key in ('baseline_total_capped_duration_s','disrupted_total_capped_duration_s','recovered_total_capped_duration_s')}})
        def merge(values):
            byid={r.request.request_id:r for r in values+unavailable}
            return tuple(byid[r.request_id] for r in requests)
        evaluation=ev.model_copy(update={'metrics':metrics,'baseline':merge(ev.baseline),'disrupted':merge(ev.disrupted),'recovered':merge(ev.recovered)})
        def objective(value):return value.model_copy(update={'total_capped_duration_s':value.total_capped_duration_s+5400*len(missing)}) if value else None
        return result.model_copy(update={'plan':result.plan.model_copy(update={'evaluation':evaluation,'objective':objective(result.plan.objective)}),'no_intervention':objective(result.no_intervention),'busiest_affected_pattern':objective(result.busiest_affected_pattern)})
    impact=apply_scenarios(snapshot,scenarios).impact
    total=5400*len(requests)
    metrics=EvaluationMetrics(request_count=len(requests),baseline_reachable_count=0,disrupted_reachable_count=0,recovered_reachable_count=0,lost_count=0,restored_count=0,restored_fraction=None,baseline_total_capped_duration_s=total,disrupted_total_capped_duration_s=total,recovered_total_capped_duration_s=total,requests_with_missed_connections=0,missed_connection_count=0)
    ev=ScenarioEvaluation(baseline=unavailable,disrupted=unavailable,recovered=unavailable,metrics=metrics,impact=impact)
    objective=RecoveryObjective(restored_count=0,total_capped_duration_s=total,bus_hours=0)
    return RecoveryResult(method="greedy_bounded_swap",budget_bus_hours=budget,plan=RecoveryPlan(candidate_ids=(),duties=(),bus_count=0,bus_hours=0,objective=objective,evaluation=ev),no_intervention=objective,busiest_affected_pattern=None,evaluated_plan_count=1,considered_candidate_ids=tuple(c.candidate_id for c in candidates))
