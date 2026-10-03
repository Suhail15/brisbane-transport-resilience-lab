"""Recompute a private pack using the matching checked-out revision."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from resilience.pipeline.reproduction import reproduce
p=argparse.ArgumentParser();p.add_argument('pack');p.add_argument('--runs',nargs='+');p.add_argument('--expected-manifest-sha256');args=p.parse_args()
print(json.dumps(reproduce(args.pack,args.runs,args.expected_manifest_sha256),indent=2))
