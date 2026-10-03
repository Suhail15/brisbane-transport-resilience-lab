"""Small display summaries; itinerary details stay lazy."""
def summary(run,inp=None,snapshot=None):
    inp=inp or {};meta=run.get('metadata',{});result=run.get('result') or {};plan=result.get('plan',{})
    names={s.stop_id:s.name for s in snapshot.stops} if snapshot else {}
    scenarios=[]
    for s in inp.get('scenarios',[]):
        targets=s.get('trip_instance_ids') or s.get('stop_ids') or [f"{x['from_stop_id']}→{x['to_stop_id']}" for x in s.get('segments',[])]
        labels=[names.get(t) or t for t in targets]
        if snapshot and s.get('trip_instance_ids'):
            labels=[]
            for tid in targets:
                cs=sorted((c for c in snapshot.connections if c.trip_instance_id==tid),key=lambda c:c.sequence)
                labels.append((names.get(cs[0].from_stop_id,cs[0].from_stop_id)+' → '+names.get(cs[-1].to_stop_id,cs[-1].to_stop_id)) if cs else tid)
        if s.get('segments') and names:labels=[names.get(x['from_stop_id'],x['from_stop_id'])+' → '+names.get(x['to_stop_id'],x['to_stop_id']) for x in s['segments']]
        scenarios.append({'kind':s['kind'],'target_ids':targets,'interval':{'start_s':s['start_s'],'end_s':s['end_s']},'readable_label':s['kind'].replace('_',' ')+' · '+', '.join(labels)})
    out={key:run.get(key) for key in ('run_id','status','snapshot_id','created_at','url')}
    out.update(version=1,source_snapshot_at=meta.get('snapshot_at'),scenario_summaries=scenarios,budget_bus_hours=meta.get('budget_bus_hours',result.get('budget_bus_hours')),used_bus_hours=plan.get('bus_hours'),sensitivity_seconds=meta.get('assumptions',{}).get('bus_running_time_sensitivity_seconds'),journey_set_version=meta.get('journey_set_version'),request_count=len(inp.get('requests',[])) if inp else None,aggregate_metrics=plan.get('evaluation',{}).get('metrics'),objective=plan.get('objective'),legacy_unversioned=not bool(meta),reproducible=run.get('reproducible',False),hypothetical=True)
    for key in ('request_set_sha256','scenario_set_sha256','candidate_set_sha256','assumptions','max_swap_evaluations','search_method','objective_version','candidate_selection_version'):out[key]=meta.get(key,inp.get(key))
    return out
