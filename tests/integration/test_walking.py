from datetime import datetime,timezone
import math
from resilience.contracts import Stop
from resilience.pipeline.archive import Archive
from resilience.pipeline.walking import build_walking

# Synthetic topology fixture verifies path/access semantics only, not real pilot coverage.
XML=b'''<osm version="0.6"><node id="1" lat="-27.500" lon="153.020"/><node id="2" lat="-27.500" lon="153.021"/><node id="3" lat="-27.500" lon="153.022"/><node id="4" lat="-27.505" lon="153.025"/><way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="footway"/><tag k="oneway:foot" v="yes"/></way><way id="11"><nd ref="3"/><nd ref="4"/><tag k="highway" v="footway"/><tag k="foot" v="no"/></way></osm>'''

def test_actual_directed_osm_paths_and_missing_connections(tmp_path):
    archive=Archive(tmp_path);at=datetime(2026,10,2,4,tzinfo=timezone.utc)
    archive.append('OSM',XML,at,'https://example.invalid')
    stops=(Stop(stop_id='a',latitude=-27.5,longitude=153.020),Stop(stop_id='b',latitude=-27.5,longitude=153.022),Stop(stop_id='far',latitude=-27.505,longitude=153.025))
    links,diag,_=build_walking(archive,stops,at)
    assert len(links)==1;link=links[0]
    assert (link.from_stop_id,link.to_stop_id)==('a','b')
    assert link.osm_node_ids==(1,2,3)
    assert link.duration_s==math.ceil(link.length_m/1.2)
    assert diag['snapped_stop_count']==2
    assert diag['status']=='incomplete'
