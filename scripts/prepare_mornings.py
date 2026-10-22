"""Reconstruct frozen receipt-bounded morning frames without upstream requests."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
from resilience.pipeline.archive import Archive
from resilience.pipeline.analysis import canonical
from resilience.pipeline.coverage import coverage_report
from resilience.pipeline.files import atomic_write
from resilience.pipeline.snapshots import build_snapshot, load_snapshot
from resilience.settings import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="configs/morning-evaluation.v1.json")
    parser.add_argument("--decision-only", action="store_true")
    parser.add_argument("--output", default="data/processed/morning-evaluation-v1/frames.json")
    args = parser.parse_args()
    plan_bytes = Path(args.plan).read_bytes()
    plan = json.loads(plan_bytes)
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    archive = Archive(settings.data_dir)
    report = coverage_report(archive)
    complete = {w["service_date"] for w in report["windows"] if w["complete"]}
    if report["complete_weekday_windows"] < 5 or not set(plan["evaluation_dates"]) <= complete:
        raise ValueError("Frozen dates require five complete original recording windows")
    root = Path(args.output).parent
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "coverage-at-preparation.json").exists():
        atomic_write(root / "coverage-at-preparation.json", canonical(report), immutable=True)
    output = Path(args.output)
    doc = json.loads(output.read_bytes()) if output.exists() else {
        "version": plan["version"], "plan_sha256": plan_hash,
        "decision_snapshots": {}, "frames": {}, "replay_snapshot_ids": [],
        "replay_label": plan["replay_label"], "status": "preparing",
    }
    if doc["plan_sha256"] != plan_hash:
        raise ValueError("Existing frame manifest belongs to a different frozen plan")
    zone = ZoneInfo(plan["timezone"])

    def frame(day, local_time):
        at = datetime.fromisoformat(day + "T" + local_time).replace(tzinfo=zone)
        key = at.isoformat()
        if key in doc["frames"]:
            item = doc["frames"][key]
            path = archive.root / "processed/snapshots" / (item["snapshot_id"] + ".json")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Existing frame bytes changed")
            snapshot = load_snapshot(archive, item["snapshot_id"])
        else:
            snapshot = build_snapshot(archive, at, store=False)
            path = archive.root / "processed/snapshots" / (snapshot.metadata.snapshot_id + ".json")
            item = {"snapshot_id": snapshot.metadata.snapshot_id,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "service_date": day, "snapshot_at": at.isoformat()}
            doc["frames"][key] = item
            atomic_write(output, canonical(doc))
            print(json.dumps({"prepared": item, "frames": len(doc["frames"])}), flush=True)
        return snapshot.metadata.snapshot_id

    # All three decisions exist before any policy results are requested.
    for day in plan["evaluation_dates"]:
        doc["decision_snapshots"][day] = frame(day, plan["decision_local_time"])
        atomic_write(output, canonical(doc))
    atomic_write(root / "decision-manifest.json", canonical({
        "version": plan["version"], "plan_sha256": plan_hash,
        "decision_snapshots": doc["decision_snapshots"],
    }), immutable=True)
    if not args.decision_only:
        for day in plan["evaluation_dates"]:
            at = datetime.fromisoformat(day + "T" + plan["replay_local_start"])
            end = datetime.fromisoformat(day + "T" + plan["replay_local_end_exclusive"])
            while at < end:
                sid = frame(day, at.time().isoformat())
                if sid not in doc["replay_snapshot_ids"]:
                    doc["replay_snapshot_ids"].append(sid)
                atomic_write(output, canonical(doc))
                at += timedelta(minutes=plan["replay_interval_minutes"])
        doc["status"] = "completed"
    else:
        doc["status"] = "decisions_prepared"
    atomic_write(output, canonical(doc))
    print(json.dumps({"manifest": str(output), "status": doc["status"],
                      "decisions": doc["decision_snapshots"],
                      "replay_frames": len(doc["replay_snapshot_ids"])}), flush=True)


if __name__ == "__main__":
    main()
