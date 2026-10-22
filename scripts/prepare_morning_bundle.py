"""Package the fixed recorded mornings; public mode retains all release guards."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
from resilience.pipeline.analysis import canonical
from resilience.pipeline.archive import Archive
from resilience.pipeline.bundle import export_bundle
from resilience.pipeline.files import atomic_write
from resilience.pipeline.snapshots import load_snapshot
from resilience.settings import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    root = Path(args.output)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Use a new empty output directory")
    plan = json.loads(Path("configs/morning-evaluation.v1.json").read_bytes())
    frames = json.loads(Path("data/processed/morning-evaluation-v1/frames.json").read_bytes())
    if frames["status"] != "completed" or len(frames["replay_snapshot_ids"]) != 72:
        raise ValueError("All 72 fixed recorded frames must be complete")
    archive = Archive(settings.data_dir)
    result = export_bundle(archive, root, public=args.public, candidate=args.candidate,
                           snapshot_ids=frames["replay_snapshot_ids"])
    catalog_path = root / "catalog.json"
    catalog = json.loads(catalog_path.read_bytes())
    if {s["service_date"] for s in catalog["snapshots"]} != set(plan["evaluation_dates"]):
        raise ValueError("Morning bundle contains an unexpected service date")
    catalog["preferred_snapshot_id"] = frames["decision_snapshots"][plan["evaluation_dates"][0]]
    catalog["source_summary"]["replay_label"] = plan["replay_label"]
    catalog["source_summary"]["walking_database_url"] = "walking/derived-walking.json.gz"
    catalog["source_summary"]["data_licences_url"] = "DATA_LICENSE.md"
    catalog["source_summary"]["attribution"] = (
        "Contains public transport data provided by Translink (Department of Transport "
        "and Main Roads, Queensland) under CC BY 4.0. Translink does not endorse and "
        "is not affiliated with this independent project or its simulation outcomes. "
        "© OpenStreetMap contributors; ODbL 1.0.")
    atomic_write(catalog_path, canonical(catalog))
    links = {}
    sources = set()
    for sid in frames["decision_snapshots"].values():
        snapshot = load_snapshot(archive, sid)
        sources.update(s.sha256 for s in snapshot.metadata.sources if s.source_kind == "osm")
        for link in snapshot.walking_links:
            item = link.model_dump(mode="json")
            if link.link_id in links and links[link.link_id] != item:
                raise ValueError("Walking identity collision across selected mornings")
            links[link.link_id] = item
    walking = {"licence": "ODbL 1.0", "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
               "attribution": "© OpenStreetMap contributors", "source_osm_sha256": sorted(sources),
               "changes": "Pilot pedestrian filtering, conservative stop associations and bounded path derivation",
               "walking_links": [links[key] for key in sorted(links)]}
    atomic_write(root / "walking/derived-walking.json.gz", gzip.compress(canonical(walking), mtime=0))
    atomic_write(root / "walking/ATTRIBUTION.txt", "© OpenStreetMap contributors. Derived walking database under ODbL 1.0: https://opendatacommons.org/licenses/odbl/1-0/\nSource paths and changes: see derived-walking.json.gz and DATA_LICENSE.md.\n")
    atomic_write(root / "DATA_LICENSE.md", Path("DATA_LICENSE.md").read_bytes())
    report_root = Path("data/processed/morning-evaluation-v1/report")
    for name in ("report.json", "metrics.csv", "origin-impacts.csv", "candidate-rejections.csv", "runtime.csv"):
        atomic_write(root / "findings" / name, (report_root / name).read_bytes())
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"] = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(root.rglob("*")) if p.is_file() and p != manifest_path}
    atomic_write(manifest_path, canonical(manifest))
    print(json.dumps({**result, "files": len(manifest["files"]),
                      "bytes": sum(p.stat().st_size for p in root.rglob("*") if p.is_file()),
                      "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
