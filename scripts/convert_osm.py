"""Convert recorded OSM XML to OTP's required PBF using official pyosmium."""
import argparse
from pathlib import Path
import osmium
p=argparse.ArgumentParser();p.add_argument("--source",default="data/bootstrap/walking.osm");p.add_argument("--output",default="data/derived/otp/walking.osm.pbf");args=p.parse_args()
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
class Copy(osmium.SimpleHandler):
    def __init__(self,writer):super().__init__();self.writer=writer
    def node(self,item):self.writer.add_node(item)
    def way(self,item):self.writer.add_way(item)
    def relation(self,item):self.writer.add_relation(item)
with osmium.SimpleWriter(str(out),overwrite=True) as writer:Copy(writer).apply_file(args.source)
print({"output":str(out),"bytes":out.stat().st_size})
