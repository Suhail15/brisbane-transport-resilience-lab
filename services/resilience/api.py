from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
from threading import Lock
from typing import Literal
import uuid
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from .pipeline.files import atomic_write
from pydantic import BaseModel,Field
from .contracts import JourneyRequest,Scenario,RecoveryCandidate
from .pipeline.analysis import (prepare_input,persist_input,available_requests,plan_with_unavailable,canonical,digest)
from .pipeline.sensitivity import stress_snapshot
from .settings import settings
from .pipeline.archive import Archive
from .pipeline.snapshots import build_snapshot,load_snapshot,snapshot_index
from .pipeline.network import network
from .pipeline.coverage import release_gate

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    reconcile_runs()
    yield

app=FastAPI(lifespan=lifespan,title="Brisbane Transport Resilience Lab",version="1")
app.add_middleware(GZipMiddleware,minimum_size=1000)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_methods=["GET","POST"],allow_headers=["Content-Type"])
archive=Archive(settings.data_dir)
executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="scenario")
lock=Lock();runs={}

class SnapshotInput(BaseModel):
    as_of: datetime
class JourneyInput(BaseModel):
    snapshot_id: str
    request: JourneyRequest
class ExperimentInput(BaseModel):
    snapshot_id: str
    requests: list[JourneyRequest]=Field(min_length=1,max_length=500)
    scenarios: list[Scenario]=Field(default_factory=list)
    budget_bus_hours: Literal[0,2,4,8]=0
    journey_set_version: str="equal-weight-fixed-requests-v1"
    bus_running_time_sensitivity_seconds: Literal[0,300,600]=0
    max_swap_evaluations: int=Field(default=128,ge=0,le=4096)

def snapshot_or_404(sid):
    try:return load_snapshot(archive,sid)
    except KeyError:raise HTTPException(404,"Unknown snapshot")

def read_run(path):
    run=json.loads(path.read_text())
    if "metadata" not in run:run.update(legacy_unversioned=True,reproducible=False)
    return run

def reconcile_runs():
    root=archive.root/"processed"/"experiments"
    for path in root.glob("*.json"):
        run=read_run(path)
        if run["status"] in ("queued","running","cancellation_requested"):
            run.update(status="failed",progress=1,result=None,error="Backend restarted before calculation completed; resubmit under a new run id",interrupted_at=datetime.now(timezone.utc).isoformat())
            atomic_write(path,json.dumps(run))

def save_run(run):
    root=archive.root/"processed"/"experiments";root.mkdir(parents=True,exist_ok=True)
    try:
        from .db import persist_run
        persist_run(run)
    except Exception as exc:run["store_warning"]=str(exc)
    path=root/f"{run['run_id']}.json"
    terminal=run["status"] in ("completed","failed","cancelled")
    # Mutable progress is separate from the immutable submitted input/metadata and final result.
    atomic_write(path,json.dumps(run))
    if terminal:
        atomic_write(archive.root/"processed"/"run-results"/path.name,canonical(run),immutable=True)

def run_job(run_id,payload,snapshot,candidates):
    from .engine import plan_recovery,generate_recovery_candidates,RecoveryCancelled
    with lock:
        run=runs[run_id]
        if run["status"]=="cancellation_requested":run.update(status="cancelled",progress=1);save_run(run);return
        run.update(status="running",progress=.1)
    try:
        with lock:run["progress"]=.2
        def should_cancel():
            with lock:return run["status"]=="cancellation_requested"
        def on_progress(value):
            with lock:
                run["progress_details"]=value.model_dump(mode="json") if hasattr(value,"model_dump") else {k:getattr(value,k) for k in ("stage","evaluated_plan_count","considered_candidate_count","feasible_candidate_count","evaluation_upper_bound")}
                if value.evaluation_upper_bound:
                    run["progress"]=min(.95,.2+.75*value.evaluated_plan_count/value.evaluation_upper_bound)
        result=plan_with_unavailable(snapshot,payload.requests,payload.scenarios,candidates,payload.budget_bus_hours,max_swap_evaluations=payload.max_swap_evaluations,on_progress=on_progress,should_cancel=should_cancel)
        with lock:
            if run["status"]=="cancellation_requested":run.update(status="cancelled",progress=1)
            else:run.update(status="completed",progress=1,result=result.model_dump(mode="json"))
    except RecoveryCancelled:
        with lock:run.update(status="cancelled",progress=1,result=None)
    except Exception as exc:
        with lock:run.update(status="failed",progress=1,error=str(exc))
    save_run(run)

@app.get("/v1/catalog")
async def catalog():
    pilot_path=Path("configs/pilot.json")
    return {"version":1,"timezone":"Australia/Brisbane","preview_only":True,"pilot":json.loads(pilot_path.read_text()) if pilot_path.exists() else None,"snapshots":snapshot_index(archive),"source_summary":{"receipt_count":len(archive.records()),"facts":"Schedules and predicted feed events; no measured passenger outcomes"},"release_gate":release_gate(archive)}

@app.get("/v1/network")
async def get_network(snapshot_id:str|None=None):
    if snapshot_id:snapshot_or_404(snapshot_id)
    return await asyncio.to_thread(network,archive,snapshot_id)

@app.get("/v1/snapshots")
async def snapshots():return {"snapshots":snapshot_index(archive)}

@app.get("/v1/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id:str):return snapshot_or_404(snapshot_id)

@app.post("/v1/snapshots",status_code=201)
async def create_snapshot(payload:SnapshotInput):
    try:return await asyncio.to_thread(build_snapshot,archive,payload.as_of)
    except ValueError as exc:raise HTTPException(409,str(exc))

@app.post("/v1/journeys")
async def journey(payload:JourneyInput):
    from .engine import route
    snapshot=snapshot_or_404(payload.snapshot_id)
    valid,missing=available_requests(snapshot,(payload.request,))
    if missing:
        from .contracts import RouteResult
        return RouteResult(request=payload.request,reachable=False,quality=snapshot.metadata.quality.model_copy(update={"warnings":snapshot.metadata.quality.warnings+("Adapter unavailable: stop absent in snapshot",)}))
    try:return await asyncio.to_thread(route,snapshot,payload.request)
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post("/v1/experiments",status_code=202)
async def create_experiment(payload:ExperimentInput):
    snapshot=snapshot_or_404(payload.snapshot_id);rid=uuid.uuid4().hex
    if len({r.request_id for r in payload.requests})!=len(payload.requests):raise HTTPException(422,"Request ids must be unique")
    if any(r.departure_s<snapshot.metadata.snapshot_s for r in payload.requests):raise HTTPException(422,"Requests cannot depart before snapshot cutoff")
    def prepare():
        from .engine import generate_recovery_candidates
        valid,missing=available_requests(snapshot,payload.requests)
        candidates=generate_recovery_candidates(snapshot,valid,payload.scenarios) if valid else ()
        effective,transform=stress_snapshot(snapshot,payload.bus_running_time_sensitivity_seconds)
        derived=None
        if payload.bus_running_time_sensitivity_seconds:
            content=canonical(effective);sha=__import__("hashlib").sha256(content).hexdigest()
            atomic_write(archive.root/"processed"/"derived-inputs"/f"{sha}.json",content,immutable=True)
            derived={**transform,"snapshot_content_sha256":sha,"path":f"derived-inputs/{sha}.json"}
        normalized,metadata=prepare_input(archive,snapshot,payload.requests,payload.scenarios,candidates,payload.budget_bus_hours,journey_set_version=payload.journey_set_version,delta=payload.bus_running_time_sensitivity_seconds,derived=derived,max_swaps=payload.max_swap_evaluations)
        persist_input(archive,rid,normalized,metadata)
        return effective,candidates,normalized,metadata,missing
    try:effective,candidates,normalized,metadata,missing=await asyncio.to_thread(prepare)
    except ValueError as exc:raise HTTPException(422,str(exc))
    run={"run_id":rid,"status":"queued","progress":0,"created_at":datetime.now(timezone.utc).isoformat(),"snapshot_id":payload.snapshot_id,"hypothetical":True,"result":None,"error":None,"input":normalized,"metadata":metadata.model_dump(mode="json"),"legacy_unversioned":False,"reproducible":True,"unavailable_request_ids":[r.request_id for r in missing],"url":f"experiments/{rid}.json"}
    with lock:runs[rid]=run
    save_run(run);executor.submit(run_job,rid,payload,effective,candidates)
    return {k:run[k] for k in ("run_id","status","progress","url")}

@app.get("/v1/experiments")
async def experiments():
    from .pipeline.integrity import recorded_runs
    try:stored=await asyncio.to_thread(recorded_runs,archive)
    except (ValueError,OSError) as exc:raise HTTPException(409,f"Recorded artifact integrity failure: {exc}")
    with lock:
        for run_id,run in runs.items():
            if not (archive.root/'processed'/'run-results'/f'{run_id}.json').exists():stored[run_id]=run
    from .pipeline.run_index import summary
    from .pipeline.integrity import verify_run,adapter_digest
    from .pipeline.analysis import engine_digest
    output=[]
    for r in stored.values():
        inp=None
        if r['status']=='completed' and (r.get('metadata') or (archive.root/'processed'/'run-results'/f"{r['run_id']}.json").exists()):
            try:
                r,inp=await asyncio.to_thread(verify_run,archive,r['run_id'],require_code=False)
                r=dict(r,reproducible=inp['engine_code_sha256']==engine_digest() and inp.get('adapter_code_sha256')==adapter_digest())
            except (ValueError,OSError) as exc:
                raise HTTPException(409,f"Recorded artifact integrity failure: {exc}")
        output.append(summary(r,inp,await asyncio.to_thread(load_snapshot,archive,r['snapshot_id']) if inp else None))
    return {"version":1,"runs":output}

@app.get("/v1/experiments/{run_id}")
async def experiment(run_id:str):
    with lock:
        if run_id in runs:return dict(runs[run_id])
    if run_id.isalnum():
        path=archive.root/"processed"/"experiments"/f"{run_id}.json"
        if path.exists():return read_run(path)
    raise HTTPException(404,"Unknown experiment")

@app.post("/v1/experiments/{run_id}/cancel")
async def cancel(run_id:str):
    with lock:
        if run_id not in runs:raise HTTPException(409,"Run is not active in this server")
        run=runs[run_id]
        if run["status"] in ("queued","running"):run["status"]="cancellation_requested"
        return dict(run)

@app.get("/v1/snapshots/{snapshot_id}/display")
async def display(snapshot_id:str):
    snapshot_or_404(snapshot_id)
    from .pipeline.display import display_frame
    return await asyncio.to_thread(display_frame,archive,snapshot_id)

@app.get("/v1/health")
async def health():
    def check():
        import psycopg
        from confluent_kafka.admin import AdminClient
        components={"archive":"ok"}
        try:
            with psycopg.connect(settings.database_url,connect_timeout=2) as db:db.execute("SELECT PostGIS_Version()").fetchone()
            components["postgis"]="ok"
        except Exception as exc:components["postgis"]=str(exc)
        try:AdminClient({"bootstrap.servers":settings.broker}).list_topics(timeout=2);components["redpanda"]="ok"
        except Exception as exc:components["redpanda"]=str(exc)
        return {"status":"ok" if all(v=="ok" for v in components.values()) else "degraded","components":components,"preview_only":True}
    return await asyncio.to_thread(check)

@app.get("/v1/snapshots/{snapshot_id}/choices")
async def get_choices(snapshot_id:str):
    snapshot_or_404(snapshot_id)
    from .pipeline.display import choices
    return await asyncio.to_thread(choices,archive,snapshot_id)
