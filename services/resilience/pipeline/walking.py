"""Directed paths on archived OSM ways, with explicit conservative stop snaps."""
from __future__ import annotations
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime
import networkx as nx
import numpy as np
from ..contracts import WalkingLink
from .files import atomic_write

MAX_SNAP_M = 30

def distance(a,b):
    lat1,lon1=map(math.radians,(a[1],a[0]));lat2,lon2=map(math.radians,(b[1],b[0]))
    return 6371008.8*2*math.asin(min(1,math.sqrt(math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2)))

def walking_source(archive):
    from .archive import utcnow
    existing=archive.latest("OSM",utcnow())
    if existing: return existing
    path=archive.root/"bootstrap"/"walking.osm"
    if not path.exists(): return None
    manifests=list(path.parent.glob("*walking*json"))+list(path.parent.glob("*osm*json"))
    info=json.loads(manifests[0].read_text()) if manifests else {}
    # Never backdate an unreceipted file: fallback receipt is import time.
    stamp=datetime.fromisoformat(info["received_at"]) if info.get("received_at") else utcnow()
    payload=path.read_bytes()
    if info.get("sha256") and hashlib.sha256(payload).hexdigest()!=info["sha256"]:raise ValueError("OSM bootstrap hash mismatch")
    return archive.append("OSM",payload,stamp,info.get("url",info.get("source_url","https://www.openstreetmap.org")),details={**info,"licence":"ODbL 1.0","publisher":"OpenStreetMap contributors"})

def build_walking(archive,stops,as_of):
    source=walking_source(archive)
    if not source or datetime.fromisoformat(source["received_at"])>as_of:
        return (), {"status":"missing","reason":"no OSM receipt available by as_of","max_snap_m":MAX_SNAP_M}, None
    cache=archive.root/"processed"/("walk-v2-"+source["sha256"]+"-"+hashlib.sha256(repr([(s.stop_id,s.latitude,s.longitude) for s in stops]).encode()).hexdigest()[:12]+".json")
    if cache.exists():
        result=json.loads(cache.read_text());return tuple(WalkingLink.model_validate(x) for x in result["links"]),result["diagnostics"],source
    root=ET.fromstring(archive.read(source)); nodes={}; blocked=set()
    for node in root.findall("node"):
        nid=int(node.attrib["id"]);nodes[nid]=(float(node.attrib["lon"]),float(node.attrib["lat"]))
        tags={tag.attrib["k"]:tag.attrib["v"] for tag in node.findall("tag")}
        if tags.get("foot") in ("no","private") or tags.get("access") in ("no","private") or tags.get("barrier") in ("wall","fence","retaining_wall"):
            blocked.add(nid)
    graph=nx.DiGraph()
    excluded={"motorway","motorway_link","trunk","trunk_link","construction","proposed","raceway"}
    for way in root.findall("way"):
        tags={tag.attrib["k"]:tag.attrib["v"] for tag in way.findall("tag")}
        if "highway" not in tags or tags["highway"] in excluded: continue
        if tags.get("foot") in ("no","private") or (tags.get("access") in ("no","private") and tags.get("foot") not in ("yes","designated","permissive")):continue
        refs=[int(n.attrib["ref"]) for n in way.findall("nd")]
        for a,b in zip(refs,refs[1:]):
            if a not in nodes or b not in nodes or a in blocked or b in blocked:continue
            length=distance(nodes[a],nodes[b]);graph.add_edge(a,b,weight=length,way_id=way.attrib["id"])
            if tags.get("oneway:foot",tags.get("foot:oneway"))!="yes":graph.add_edge(b,a,weight=length,way_id=way.attrib["id"])
    # Only pilot geography has been extracted. Preserve outside stops but mark them unverified.
    pilot=[s for s in stops if -27.523<=s.latitude<=-27.452 and 153.006<=s.longitude<=153.047]
    nids=list(graph.nodes);xy=np.array([nodes[n] for n in nids]); snaps={}; diagnostics=[]
    for stop in pilot:
        squared=((xy[:,0]-stop.longitude)*math.cos(math.radians(stop.latitude)))**2+(xy[:,1]-stop.latitude)**2
        idx=int(np.argmin(squared)); nid=nids[idx]; offset=distance((stop.longitude,stop.latitude),nodes[nid])
        diagnostics.append({"stop_id":stop.stop_id,"osm_node_id":nid,"snap_distance_m":round(offset,3),"eligible":offset<=MAX_SNAP_M})
        if offset<=MAX_SNAP_M:snaps[stop.stop_id]=(nid,offset)
    bynode={}
    for sid,(nid,offset) in snaps.items():bynode.setdefault(nid,[]).append((sid,offset))
    links=[]
    for from_sid,(start,start_offset) in sorted(snaps.items()):
        lengths,paths=nx.single_source_dijkstra(graph,start,cutoff=600-start_offset,weight="weight")
        for end,length in lengths.items():
            if end not in bynode:continue
            for to_sid,end_offset in bynode[end]:
                total=length+start_offset+end_offset
                if from_sid==to_sid or total>600 or len(paths[end])<2:continue
                path=paths[end]
                links.append(WalkingLink(link_id=f"osm:{from_sid}:{to_sid}",from_stop_id=from_sid,to_stop_id=to_sid,length_m=length,duration_s=math.ceil(length/1.2),from_snap_distance_m=start_offset,to_snap_distance_m=end_offset,osm_node_ids=tuple(path),geometry=tuple(nodes[n] for n in path)))
    diag={"status":"incomplete","max_snap_m":MAX_SNAP_M,"pilot_stop_count":len(pilot),"all_retained_stop_count":len(stops),"snapped_stop_count":len(snaps),"directed_link_count":len(links),"graph_nodes":len(graph),"graph_edges":graph.number_of_edges(),"stops":diagnostics,"limitations":["Outside extracted pilot no walking coverage","Path length and duration contain actual OSM edges only; endpoint snap association distances guard the 600m limit","Snap diagnostics establish stop association only; unseen entrance/platform connector walks are unresolved, never verified or drawn","Disconnected platforms and stops beyond 30m snap remain missing; no straight-line substitute","OSM access tags are source observations, not accessibility certification"]}
    atomic_write(cache,json.dumps({"links":[x.model_dump(mode="json") for x in links],"diagnostics":diag}),immutable=True)
    (archive.root/"processed"/"walking-audit.json").write_text(json.dumps(diag,indent=2))
    return tuple(links),diag,source
