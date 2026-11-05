import json
import random

from shapely.affinity import translate
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

from .common import area_polygon, opt, origin_xy, write_json


def _union(parts):
    return unary_union([Polygon(p["o"], p["i"]).buffer(0) for p in parts])


def build(area):
    rng = random.Random(opt(area, "trees.seed", 42))      # same trees every run
    city = json.loads((area.site_dir / "buildings.json").read_text())
    ground = json.loads((area.site_dir / "ground.json").read_text())

    ox, oy = origin_xy(area)
    bounds = translate(area_polygon(area, area.crs), -ox, -oy)   # area box in local metres

    buildings = unary_union([Polygon(b["p"]).buffer(0) for b in city["buildings"] if len(b["p"]) >= 3])
    roads = _union(ground["roads"])
    green = _union(ground["green"])
    blocked = prep(unary_union([buildings.buffer(2.5), roads.buffer(0.5)]))

    trees, counts = [], {"street": 0, "park": 0, "open": 0}

    def add(pt, kind, smin, smax):
        if bounds.contains(pt) and not blocked.contains(pt):
            trees.append([round(pt.x, 1), round(pt.y, 1), round(rng.uniform(smin, smax), 2)])
            counts[kind] += 1
            return True
        return False

    # 1. Street trees along a line just outside every road edge
    spacing = opt(area, "trees.street_spacing_m", 15)
    edge = roads.buffer(3.5).boundary
    for line in getattr(edge, "geoms", [edge]):
        d = 0.0
        while d < line.length:
            if rng.random() < 0.75:
                add(line.interpolate(d + rng.uniform(-2, 2)), "street", 0.9, 1.4)
            d += spacing

    # 2 and 3. Scatter trees inside a region
    def scatter(region, m2_per_tree, kind, smin, smax):
        region = region.intersection(bounds)
        if region.is_empty:
            return
        target = int(region.area / m2_per_tree)
        inside = prep(region)
        minx, miny, maxx, maxy = region.bounds
        placed = tries = 0
        while placed < target and tries < target * 60:
            tries += 1
            pt = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
            if inside.contains(pt) and add(pt, kind, smin, smax):
                placed += 1

    scatter(green, opt(area, "trees.park_m2_per_tree", 250), "park", 0.9, 1.6)

    open_land = bounds.difference(unary_union([buildings.buffer(3), roads.buffer(1), green]))
    open_land = unary_union([g for g in getattr(open_land, "geoms", [open_land]) if g.area > 150])
    scatter(open_land, opt(area, "trees.open_m2_per_tree", 500), "open", 0.8, 1.5)

    kb = write_json(area.site_dir / "trees.json", {"trees": trees})
    print(f"  {len(trees)} trees {counts} -> trees.json ({kb:.0f} KB)")