"""Secondary exact-source ticketing proxy; never changes primary analysis."""
import io,json,zipfile
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timedelta
from fractions import Fraction
from zoneinfo import ZoneInfo
import pandas as pd
from .analysis import canonical,digest
from .integrity import verify_run,sha
from .files import atomic_write

BINS=('Weekday (12:00am-8:29:59am)','Weekday (8:30am-2:59:59pm)','Weekday (3:00pm-6:59:59pm)','Weekday (7:00pm-11:59:59pm)')
def capped_duration(route):
    return min(5400,route['arrival_s']-route['request']['departure_s']) if route['reachable'] else 5400
def fraction(value):return {'numerator':value.numerator,'denominator':value.denominator}
def time_bin(service_date,seconds):
    at=datetime.fromisoformat(service_date).replace(tzinfo=ZoneInfo('Australia/Brisbane'))+timedelta(seconds=seconds)
    wall=at.hour*3600+at.minute*60+at.second
    return 'Weekend' if at.weekday()>=5 else BINS[0 if wall<30600 else 1 if wall<54000 else 2 if wall<68400 else 3]

def build_proxy(archive,run_ids,output,*,operator_binding=None):
    if operator_binding:
        if digest(operator_binding.get('references',[]))!=operator_binding.get('evidence_sha256'):raise ValueError('Operator reference identity mismatch')
        for ref in operator_binding['references']:
            if sha(Path(ref['path']).read_bytes())!=ref['sha256']:raise ValueError('Operator evidence bytes changed')
    runs=[verify_run(archive,rid) for rid in run_ids];inp=runs[0][1]
    if any(x[1]['requests']!=inp['requests'] for x in runs):raise ValueError('Proxy requires the identical fixed requests')
    cutoff=datetime.fromisoformat(inp['snapshot_at']);od=archive.latest('MONTHLY_OD',cutoff)
    if not od:raise ValueError('No eligible monthly source receipt')
    gtfs=next(archive.get(sid) for sid in inp['source_record_ids'] if archive.get(sid)['feed']=='GTFS')
    z=zipfile.ZipFile(io.BytesIO(archive.read(gtfs)))
    def table(name):
        try:return pd.read_csv(z.open(name+'.txt'),dtype=str,keep_default_na=False)
        except KeyError:return pd.DataFrame()
    routes=table('routes');trips=table('trips');st=table('stop_times');agency=table('agency')
    service_date=json.loads((archive.root/'processed/snapshots'/f"{inp['snapshot_id']}.json").read_bytes())['metadata']['service_date']
    day=datetime.fromisoformat(service_date);stamp=day.strftime('%Y%m%d');calendar=table('calendar');exceptions=table('calendar_dates');active=set()
    if not calendar.empty:active=set(calendar[(calendar.start_date<=stamp)&(calendar.end_date>=stamp)&(calendar[day.strftime('%A').lower()]=='1')].service_id)
    if not exceptions.empty:
        for row in exceptions[exceptions.date==stamp].itertuples():
            if row.exception_type=='1':active.add(row.service_id)
            elif row.exception_type=='2':active.discard(row.service_id)
    pairs=sorted({(r['origin_stop_id'],r['destination_stop_id']) for r in inp['requests']});pairset=set(pairs)
    oz=zipfile.ZipFile(io.BytesIO(archive.read(od)));csv=next(n for n in oz.namelist() if n.lower().endswith('.csv'))
    rows=[];offset=0
    for chunk in pd.read_csv(oz.open(csv),dtype=str,keep_default_na=False,chunksize=100000):
        mask=pd.MultiIndex.from_frame(chunk[['ORIGIN_STOP','DESTINATION_STOP']]).isin(pairs)
        for index,row in chunk[mask].iterrows():rows.append(dict(row,source_row_id=int(index)+2))
        offset+=len(chunk)
    selected=defaultdict(list)
    for row in rows:selected[(row['ORIGIN_STOP'],row['DESTINATION_STOP'])].append(row)
    mappings=[];weights={};included=[];excluded=[]
    service_date=json.loads((archive.root/'processed/snapshots'/f"{inp['snapshot_id']}.json").read_bytes())['metadata']['service_date']
    for a,b in pairs:
        raw=selected[(a,b)];mapping={'origin_stop_id':a,'destination_stop_id':b,'status':'unknown','reason':'No exact raw monthly OD row','source_row_ids':[r['source_row_id'] for r in raw]}
        if raw:
            identities={(r['OPERATOR'],r['ROUTE'],r['DIRECTION']) for r in raw}
            if len(identities)!=1:mapping['reason']='Ambiguous operator/route/direction source rows'
            else:
                operator,route,direction=next(iter(identities));rids=set(routes[routes.route_short_name==route].route_id);ts=trips[trips.route_id.isin(rids)]
                subset=st[st.trip_id.isin(ts.trip_id)&st.stop_id.isin((a,b))].copy();subset['sequence']=pd.to_numeric(subset.stop_sequence)
                proof=[]
                for tid,group in subset.groupby('trip_id',sort=True):
                    aa=group[group.stop_id==a];bb=group[group.stop_id==b]
                    if len(aa)==1 and len(bb)==1 and int(aa.iloc[0].sequence)<int(bb.iloc[0].sequence):
                        tr=ts[ts.trip_id==tid].iloc[0];proof.append({'trip_id':tid,'route_id':tr.route_id,'direction_id':tr.direction_id,'origin_sequence':int(aa.iloc[0].sequence),'destination_sequence':int(bb.iloc[0].sequence)})
                full_feed_count=len(proof)
                proof=[p for p in proof if ts[ts.trip_id==p['trip_id']].iloc[0].service_id in active]
                eligible=[]
                for p in proof:
                    full=st[st.trip_id==p['trip_id']].copy();full['sequence']=pd.to_numeric(full.stop_sequence);full=full.sort_values('sequence')
                    origin=full[full.stop_sequence==str(p['origin_sequence'])].iloc[0];destination=full[full.stop_sequence==str(p['destination_sequence'])].iloc[0]
                    if origin.get('pickup_type','0')=='1' or destination.get('drop_off_type','0')=='1':continue
                    p.update(service_date=service_date,service_id=ts[ts.trip_id==p['trip_id']].iloc[0].service_id,ordered_stop_ids=list(full.stop_id),pickup_allowed=True,drop_off_allowed=True);eligible.append(p)
                proof=eligible;dirs={p['direction_id'] for p in proof}
                mapping.update(operator=operator,public_route=route,source_direction=direction,gtfs_directions=sorted(dirs),ordered_trip_proof=proof,whole_feed_ordered_trip_count=full_feed_count,dated_eligible_trip_count=len(proof),service_date=service_date)
                # A single umbrella agency does not prove this OD operator. An explicit,
                # independently reviewed source-specific binding is required in that case.
                matched_routes=routes[routes.route_id.isin({p['route_id'] for p in proof})]
                if 'agency_id' in matched_routes and 'agency_id' in agency:
                    route_operators=set(agency[agency.agency_id.isin(set(matched_routes.agency_id))].agency_name)
                    direct_operator=bool(len(route_operators)==1 and operator in route_operators and all(aid in set(agency.agency_id) for aid in matched_routes.agency_id))
                else:direct_operator=len(agency)==1 and operator==agency.iloc[0].agency_name
                bound=bool(operator_binding and operator_binding.get('operator')==operator and operator_binding.get('public_route')==route and operator_binding.get('gtfs_sha256')==gtfs['sha256'] and operator_binding.get('approved') is True and operator_binding.get('evidence_sha256'))
                if len(dirs)!=1:mapping['reason']='No unique ordered direct GTFS direction'
                elif not (direct_operator or bound):mapping['reason']='GTFS only identifies umbrella agency; exact operator binding unavailable'
                else:
                    mapping.update(status='mapped',reason=None,operator_binding=operator_binding if bound else 'exact GTFS agency name')
                    requests=[r for r in inp['requests'] if r['origin_stop_id']==a and r['destination_stop_id']==b]
                    bins=defaultdict(list)
                    for r in requests:bins[time_bin(service_date,r['departure_s'])].append(r)
                    for name,reqs in bins.items():
                        binrows=[row for row in raw if row['TIME_GROUPING']==name];q=Fraction(0);ticket=set();valid=[]
                        categories=[row['TICKET_TYPE'] for row in binrows]
                        if len(categories)!=len(set(categories)):
                            excluded.extend(dict(row,reason='Overlapping ticket categories invalidate entire pair/bin') for row in binrows)
                            continue
                        for row in binrows:
                            try:
                                value=Fraction(row['QUANTITY']);category=row['TICKET_TYPE']
                                if value<0 or category in ticket:raise ValueError('Negative or duplicate ticket category')
                                ticket.add(category);q+=value;valid.append(row)
                            except (ValueError,ZeroDivisionError):excluded.append(dict(row,reason='Invalid quantity or overlapping ticket category'))
                        if not valid:continue
                        included.extend(valid)
                        for r in reqs:weights[r['request_id']]={'weight':fraction(q/len(reqs)),'bin':name,'bin_quantity':fraction(q),'configured_departures':len(reqs),'source_row_ids':[row['source_row_id'] for row in valid]}
        if mapping['status']!='mapped':excluded.extend(dict(row,reason=mapping['reason']) for row in raw)
        mappings.append(mapping)
    totals=[]
    for run,_ in runs:
        ev=run['result']['plan']['evaluation'];by={k:{r['request']['request_id']:r for r in ev[k]} for k in ('baseline','disrupted','recovered')}
        reach=lambda r:bool(r['reachable']) and r['arrival_s']-r['request']['departure_s']<=3600
        total=Fraction(0);quantities={k:Fraction(0) for k in ('baseline','disrupted','recovered','lost','restored')};cap={k:Fraction(0) for k in by}
        for rid,item in weights.items():
            w=Fraction(**item['weight']);total+=w;flags={k:reach(by[k][rid]) for k in by}
            for k in by:
                r=by[k][rid];quantities[k]+=w if flags[k] else 0;cap[k]+=w*capped_duration(r)
            lost=flags['baseline'] and not flags['disrupted'];quantities['lost']+=w if lost else 0;quantities['restored']+=w if lost and flags['recovered'] else 0
        totals.append({'run_id':run['run_id'],'immutable_result_sha256':sha((archive.root/'processed/run-results'/f"{run['run_id']}.json").read_bytes()),'quantities':{k:fraction(v) for k,v in quantities.items()},'restored_fraction':fraction(quantities['restored']/quantities['lost']) if quantities['lost'] else None,'mean_capped_duration_s':{k:fraction(v/total) if total else None for k,v in cap.items()}})
    report={'method_code_sha256':sha(Path(__file__).read_bytes()),'version':'monthly-ticketing-query-proxy-v1','classification':'Secondary monthly ticketing-weighted query proxy; not passenger demand or savings','used_in_primary_search':False,'source':od,'gtfs_source':gtfs,'source_rows':offset,'mapped_pairs':sum(m['status']=='mapped' for m in mappings),'configured_pairs':len(pairs),'mapped_requests':len(weights),'configured_requests':len(inp['requests']),'total_proxy_weight':fraction(sum((Fraction(**i['weight']) for i in weights.values()),Fraction(0))),'mappings':mappings,'weights':weights,'included_rows':included,'excluded_rows':excluded,'results':totals}
    report['identity_sha256']=digest(report);atomic_write(output,canonical(report),immutable=True);return report
