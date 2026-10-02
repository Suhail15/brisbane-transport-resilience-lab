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
from .settings import settings
from .pipeline.archive import Archive
from .pipeline.snapshots import build_snapshot,load_snapshot,snapshot_index
from .pipeline.network import network
from .pipeline.coverage import release_gate

app=FastAPI(title="Brisbane Transport Resilience Lab",version="1")
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

def snapshot_or_404(sid):
    try:return load_snapshot(archive,sid)
    except KeyError:raise HTTPException(404,"Unknown snapshot")

def save_run(run):
    root=archive.root/"processed"/"experiments";root.mkdir(parents=True,exist_ok=True)
    atomic_write(root/f"{run['run_id']}.json",json.dumps(run),immutable=False)
    try:
        from .db import persist_run
        persist_run(run)
    except Exception as exc:run["store_warning"]=str(exc)

def run_job(run_id,payload,snapshot):
    from .engine import plan_recovery,generate_recovery_candidates,RecoveryCancelled
    with lock:
        run=runs[run_id]
        if run["status"]=="cancellation_requested":run.update(status="cancelled",progress=1);save_run(run);return
        run.update(status="running",progress=.1)
    try:
        candidates=generate_recovery_candidates(snapshot,payload.requests,payload.scenarios)
        with lock:run["progress"]=.2
        def should_cancel():
            with lock:return run["status"]=="cancellation_requested"
        def on_progress(value):
            with lock:
                run["progress_details"]=value.model_dump(mode="json") if hasattr(value,"model_dump") else {k:getattr(value,k) for k in ("stage","evaluated_plan_count","considered_candidate_count","feasible_candidate_count","evaluation_upper_bound")}
                if value.evaluation_upper_bound:
                    run["progress"]=min(.95,.2+.75*value.evaluated_plan_count/value.evaluation_upper_bound)
        result=plan_recovery(snapshot,payload.requests,payload.scenarios,candidates,payload.budget_bus_hours,on_progress=on_progress,should_cancel=should_cancel)
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
    try:return await asyncio.to_thread(route,snapshot,payload.request)
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post("/v1/experiments",status_code=202)
async def create_experiment(payload:ExperimentInput):
    snapshot=snapshot_or_404(payload.snapshot_id);rid=uuid.uuid4().hex
    run={"run_id":rid,"status":"queued","progress":0,"created_at":datetime.now(timezone.utc).isoformat(),"snapshot_id":payload.snapshot_id,"hypothetical":True,"result":None,"error":None,"input":payload.model_dump(mode="json"),"url":f"experiments/{rid}.json"}
    with lock:runs[rid]=run
    save_run(run);executor.submit(run_job,rid,payload,snapshot)
    return {k:run[k] for k in ("run_id","status","progress","url")}

@app.get("/v1/experiments")
async def experiments():
    root=archive.root/"processed"/"experiments";stored={p.stem:json.loads(p.read_text()) for p in root.glob("*.json")}
    with lock:stored.update(runs)
    return {"runs":[{k:r[k] for k in ("run_id","status","progress","url")} for r in stored.values()]}

@app.get("/v1/experiments/{run_id}")
async def experiment(run_id:str):
    with lock:
        if run_id in runs:return dict(runs[run_id])
    if run_id.isalnum():
        path=archive.root/"processed"/"experiments"/f"{run_id}.json"
        if path.exists():return json.loads(path.read_text())
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
