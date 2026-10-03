"""Fail closed before deployment; verify prepared bytes and scoped evidence."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from resilience.pipeline.archive import Archive
from resilience.pipeline.coverage import release_gate
from resilience.pipeline.integrity import verify_manifest_files,sha
p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--data-dir',default='data');args=p.parse_args()
gate=release_gate(Archive(Path(args.data_dir)))
root=Path(args.bundle);manifest=json.loads((root/'manifest.json').read_bytes())
from resilience.pipeline.evidence import release_evidence
evidence=release_evidence()
report_ref=evidence.get('public_artifacts',{}).get('report')
if not report_ref:raise SystemExit('Release blocked: no reviewed public manifest report')
report=json.loads(Path(report_ref).read_bytes())
if report.get('public_manifest_sha256')!=sha((root/'manifest.json').read_bytes()):raise SystemExit('Release blocked: supplied manifest differs from reviewed public candidate')
if manifest.get('public') is not True:raise SystemExit('Release blocked: private preview bundle')
verify_manifest_files(root,manifest['files'])
if not gate['passed']:raise SystemExit('Release blocked: '+', '.join(gate['blocking']))
print('Verified public artifact bytes and all scoped release evidence')
