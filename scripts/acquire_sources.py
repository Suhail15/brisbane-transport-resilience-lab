"""Cross-platform local source acquisition. Originals stay ignored in the archive."""
import sys
from pathlib import Path
import json
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from resilience.settings import settings
from resilience.pipeline.archive import Archive,utcnow
from resilience.pipeline.collector import refresh_schedule

archive=Archive(settings.data_dir)
print(refresh_schedule(archive))
query='[out:xml][timeout:60];way["highway"](-27.523,153.006,-27.452,153.047);(._;>;);out body;'
errors=[]
for endpoint in ('https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter'):
    try:
        response=httpx.post(endpoint,data={'data':query},timeout=100);response.raise_for_status()
        print(archive.append('OSM',response.content,utcnow(),endpoint,details={'query':query,'licence':'ODbL 1.0','publisher':'OpenStreetMap contributors'}));break
    except Exception as exc:errors.append(str(exc))
else:raise SystemExit('Both OSM acquisitions failed; report these errors before retrying: '+repr(errors))
