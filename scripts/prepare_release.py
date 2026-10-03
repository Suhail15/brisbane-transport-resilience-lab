"""Prepare reviewed private artifacts; no publishing or permission changes."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from resilience.pipeline.archive import Archive
from resilience.pipeline.bundle import export_bundle
from resilience.pipeline.reproduction import pack
from resilience.pipeline.coverage import release_gate
p=argparse.ArgumentParser();p.add_argument('--data-dir',default='data');p.add_argument('--bundle');p.add_argument('--pack');p.add_argument('--runs',nargs='+');p.add_argument('--extras',nargs='*',default=[]);args=p.parse_args();ar=Archive(Path(args.data_dir));out={'release_gate':release_gate(ar)}
if args.bundle:out['bundle']=export_bundle(ar,Path(args.bundle),public=False)
if args.pack:
 if not args.runs:p.error('--pack requires explicit reviewed --runs')
 out['pack']=pack(ar,Path(args.pack),args.runs,args.extras)
print(json.dumps(out,indent=2))
