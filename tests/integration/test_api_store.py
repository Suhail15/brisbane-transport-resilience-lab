import os
from pathlib import Path
from fastapi.testclient import TestClient
from resilience.api import app

def test_api_invalid_ids_and_release_state():
    with TestClient(app) as client:
        catalog=client.get('/v1/catalog').json()
        assert catalog['version']==1 and catalog['preview_only'] is True
        assert client.get('/v1/snapshots/doesnotexist').status_code==404
        assert client.post('/v1/experiments',json={'snapshot_id':'bad','requests':[]}).status_code==422
        assert client.post('/v1/snapshots',json={'as_of':'2020-01-01T00:00:00+00:00'}).status_code==409

# Opt in to real infrastructure checks; fixture-only CI never claims external coverage.
def test_postgis_spatial_snapshot_if_enabled():
    if os.getenv('RESILIENCE_INTEGRATION_DB')!='1':
        import pytest;pytest.skip('real infrastructure opt-in')
    import psycopg
    from resilience.settings import settings
    with psycopg.connect(settings.database_url) as db:
        assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0]>0
        count=db.execute('SELECT count(*) FROM stops WHERE ST_DWithin(geometry::geography,ST_SetSRID(ST_MakePoint(153.025,-27.5),4326)::geography,3000)').fetchone()[0]
        assert count>0
        assert db.execute('SELECT count(*) FROM walking_links WHERE ST_NPoints(geometry)>=2').fetchone()[0]>0
