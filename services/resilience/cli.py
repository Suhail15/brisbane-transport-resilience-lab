from __future__ import annotations
import argparse
import json
from datetime import datetime
from .settings import settings
from .pipeline.archive import Archive

def main():
    parser = argparse.ArgumentParser(prog="resilience")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap")
    collection = sub.add_parser("collect"); collection.add_argument("--force", action="store_true"); collection.add_argument("--once", action="store_true")
    sub.add_parser("audit")
    snapshot = sub.add_parser("snapshot"); snapshot.add_argument("--as-of", required=True)
    sub.add_parser("store")
    sub.add_parser("coverage")
    sub.add_parser("audit-od")
    export = sub.add_parser("export"); export.add_argument("--output", default="data/derived/demo"); export.add_argument("--public", action="store_true"); export.add_argument("--candidate", action="store_true",help="Prepare eligible public projection locally without final artifact gates; never authorizes publication")
    sub.add_parser("release-gate")
    args = parser.parse_args()
    archive = Archive(settings.data_dir)
    if args.command == "bootstrap": print(json.dumps(archive.import_bootstrap(), indent=2))
    elif args.command == "collect":
        from .pipeline.collector import collect
        collect(archive, force=args.force, once=args.once)
    elif args.command == "audit":
        from .pipeline.schedule import audit_pilot
        print(json.dumps(audit_pilot(archive), indent=2))
    elif args.command == "snapshot":
        from .pipeline.snapshots import build_snapshot
        result = build_snapshot(archive, datetime.fromisoformat(args.as_of)); print(result.metadata.model_dump_json(indent=2))
    elif args.command == "store":
        from .db import initialize, flush_outbox
        initialize(); print(flush_outbox(archive))
    elif args.command == "audit-od":
        from .pipeline.od import audit_od
        print(json.dumps(audit_od(archive),indent=2))
    elif args.command == "coverage":
        from .pipeline.coverage import coverage_report
        print(json.dumps(coverage_report(archive), indent=2))
    elif args.command == "export":
        from .pipeline.bundle import export_bundle
        print(export_bundle(archive, args.output, public=args.public,candidate=args.candidate))
    elif args.command == "release-gate":
        from .pipeline.coverage import release_gate
        result = release_gate(archive); print(json.dumps(result, indent=2)); raise SystemExit(0 if result["passed"] else 1)

if __name__ == "__main__": main()
