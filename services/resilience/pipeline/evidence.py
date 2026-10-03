"""Evidence identities bind a gate to concrete bytes and a reviewed revision."""
import json
import subprocess
from pathlib import Path
from .integrity import sha

def evidence_check(item,*,name,revision,root=Path('.')):
    try:
        if not revision or not item.get('report') or not item.get('sha256'):return False,'Missing hashed report or candidate revision'
        path=root/item['report'];data=path.read_bytes()
        if sha(data)!=item['sha256']:return False,'Report hash mismatch'
        report=json.loads(data)
        if report.get('gate')!=name or report.get('candidate_revision')!=revision or report.get('passed') is not True:return False,'Report scope/revision/result mismatch'
        if not report.get('scope') or not report.get('checks'):return False,'Missing scope or actual checks'
        for check in report['checks']:
            ref=check.get('evidence',{})
            if check.get('passed') is not True or not isinstance(ref,dict) or not ref.get('path') or not ref.get('sha256'):return False,'Missing hashed check artifact'
            if sha((root/ref['path']).read_bytes())!=ref['sha256']:return False,'Check artifact hash mismatch'
        if name=='performance' and not (report.get('sample_count',0)>=100 and 0<=report.get('p95_seconds',float('inf'))<2):return False,'Performance workload/threshold missing'
        if name=='licences' and report.get('publisher_approval_received') is not True:return False,'Publisher approval pending'
        if name=='public_artifacts' and not report.get('public_manifest_sha256'):return False,'Public manifest identity missing'
        acceptance=report.get('acceptance',{})
        if acceptance.get('reviewer') not in ('root','architecture') or not acceptance.get('reference') or not acceptance.get('sha256'):return False,'Missing concrete manual acceptance'
        if sha((root/acceptance['reference']).read_bytes())!=acceptance['sha256']:return False,'Acceptance hash mismatch'
        return True,None
    except (OSError,ValueError,TypeError,KeyError):return False,'Missing or invalid evidence artifact'

def candidate_revision():
    try:return subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    except (OSError,subprocess.CalledProcessError):return None


def candidate_code_clean():
    """Generated ignored data is allowed; every nonignored checkout file is frozen."""
    try:return not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],text=True).strip()
    except (OSError,subprocess.CalledProcessError):return False

def release_evidence():
    import os
    path=Path(os.environ.get('RESILIENCE_RELEASE_EVIDENCE','configs/release-evidence.json'))
    return json.loads(path.read_bytes()) if path.exists() else {}
