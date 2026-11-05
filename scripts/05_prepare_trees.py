import json
import random
from pathlib import Path

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union
from shapely.prepared import prep

random.seed(42)                                   # same trees every run
OUT = Path("web3d/trees.json")

city = json.loads(Path("web3d/buildings.json").read_text())
ground = json.loads(Path("web3d/ground.json").read_text())

# Everything here is already in local metres (x = east, y = north)
buildings = unary_union([Polygon(b["p"]).buffer(0) for b in city["buildings"] if len(b["p"]) >= 3])
roads = unary_union([Polygon(p["o"], p["i"]).buffer(0) for p in ground["roads"]])
green = unary_union([Polygon(p["o"], p["i"]).buffer(0) for p in ground["green"]])
area = box(*buildings.bounds)

blocked = prep(unary_union([buildings.buffer(2.5), roads.buffer(0.5)]))
trees, counts = [], {"street": 0, "park": 0, "open": 0}

def add(pt, kind, smin, smax):
    if area.contains(pt) and not blocked.contains(pt):
        trees.append([round(pt.x, 1), round(pt.y, 1), round(random.uniform(smin, smax), 2)])
        counts[kind] += 1
        return True
    return False

# 1. Street trees: along a line 3.5 m outside every road edge, about every 15 m
edge = roads.buffer(3.5).boundary
for line in getattr(edge, "geoms", [edge]):
    d = 0.0
    while d < line.length:
        if random.random() < 0.75:
            add(line.interpolate(d + random.uniform(-2, 2)), "street", 0.9, 1.4)
        d += 15

# 2 and 3. Scatter trees randomly inside a region
def scatter(region, m2_per_tree, kind, smin, smax):
    region = region.intersection(area)
    target = int(region.area / m2_per_tree)
    inside = prep(region)
    minx, miny, maxx, maxy = region.bounds
    placed = tries = 0
    while placed < target and tries < target * 60:
        tries += 1
        pt = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
        if inside.contains(pt) and add(pt, kind, smin, smax):
            placed += 1

scatter(green, 250, "park", 0.9, 1.6)

open_land = area.difference(unary_union([buildings.buffer(3), roads.buffer(1), green]))
open_land = unary_union([g for g in getattr(open_land, "geoms", [open_land]) if g.area > 150])
scatter(open_land, 500, "open", 0.8, 1.5)

OUT.write_text(json.dumps({"trees": trees}, separators=(",", ":")))
print(f"{len(trees)} trees -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
print(counts)