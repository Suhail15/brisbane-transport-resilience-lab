"""Portable launcher: python scripts/start.py infra|api|collect|prepare|check."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('mode',choices=['infra','api','collect','prepare','check']);p.add_argument('--force',action='store_true');args=p.parse_args()
os.chdir(ROOT)
env={**os.environ,'PYTHONPATH':str(ROOT/'services')}
def run(command):subprocess.run(command,check=True,env=env)
if args.mode=='infra':run(['docker','compose','up','-d','postgres','redpanda'])
elif args.mode=='api':run([sys.executable,'-m','uvicorn','resilience.api:app','--host','127.0.0.1','--port','8000'])
elif args.mode=='collect':run([sys.executable,'-m','resilience.cli','collect',*(['--force'] if args.force else [])])
elif args.mode=='prepare':
    run([sys.executable,'scripts/acquire_sources.py']);run([sys.executable,'-m','resilience.cli','audit']);run([sys.executable,'-m','resilience.cli','store'])
else:run([sys.executable,'-m','pytest','-q'])
