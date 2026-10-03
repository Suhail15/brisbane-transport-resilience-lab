"""Prepare/install a user-owned scheduled collector; no credentials or system service."""
import argparse
from datetime import date
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];LABEL='au.brisbane.transport-resilience.collector'
p=argparse.ArgumentParser();p.add_argument('--install',action='store_true');p.add_argument('--remove',action='store_true');args=p.parse_args()
logs=ROOT/'data/runtime';logs.mkdir(parents=True,exist_ok=True)
if sys.platform=='darwin':
    path=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    definition={'Label':LABEL,'ProgramArguments':[sys.executable,'-m','resilience.cli','collect'],'WorkingDirectory':str(ROOT),'EnvironmentVariables':{'PYTHONPATH':str(ROOT/'services'),'PYTHONUNBUFFERED':'1'},'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'StandardOutPath':str(logs/'scheduled-collector.log'),'StandardErrorPath':str(logs/'scheduled-collector-error.log'),'ProcessType':'Background'}
    staging=logs/'collector-launchagent.plist';staging.write_bytes(plistlib.dumps(definition))
    if args.remove:
        subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{LABEL}'],check=False)
        if path.exists():path.unlink()
    elif args.install:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(staging.read_bytes());subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(path)],check=True)
    print({'prepared':str(staging),'installed_path':str(path),'install_requested':args.install,'scheduled':'Process waits outside weekdays06–12; awake assertion exists only inside window'})
elif os.name=='nt':
    # User logon starts a single portable recorder; OS task restarts failed process.
    ns='http://schemas.microsoft.com/windows/2004/02/mit/task';ET.register_namespace('',ns)
    def add(parent,name,text=None):node=ET.SubElement(parent,'{'+ns+'}'+name);node.text=text;return node
    task=ET.Element('{'+ns+'}Task',{'version':'1.2'});triggers=add(task,'Triggers');trigger=add(triggers,'LogonTrigger');add(trigger,'Enabled','true')
    settings=add(task,'Settings');add(settings,'MultipleInstancesPolicy','IgnoreNew');add(settings,'DisallowStartIfOnBatteries','false');add(settings,'StopIfGoingOnBatteries','false');add(settings,'StartWhenAvailable','true');add(settings,'ExecutionTimeLimit','PT0S');restart=add(settings,'RestartOnFailure');add(restart,'Interval','PT1M');add(restart,'Count','999')
    actions=add(task,'Actions');execute=add(actions,'Exec');add(execute,'Command',sys.executable);add(execute,'Arguments','"'+str(ROOT/'scripts/start.py')+'" collect');add(execute,'WorkingDirectory',str(ROOT))
    path=logs/'collector-task.xml';ET.ElementTree(task).write(path,encoding='utf-16',xml_declaration=True)
    if args.remove:subprocess.run(['schtasks','/Delete','/TN',LABEL,'/F'],check=True)
    elif args.install:subprocess.run(['schtasks','/Create','/TN',LABEL,'/XML',str(path),'/F'],check=True);subprocess.run(['schtasks','/Run','/TN',LABEL],check=True)
    print({'prepared':str(path),'install_requested':args.install,'scheduled':'Logged-in user process waits outside weekdays06–12; window-only Windows execution-state sleep assertion'})
else:raise SystemExit('Automatic service installer supports macOS/Windows; use a user process manager on Linux')
