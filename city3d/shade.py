import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from shapely.affinity import rotate, scale
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import unary_union
from suncalc import get_position

from .common import opt, write_json

# Same tree shape as the 3D viewer: crown centre 5.5 m up, radius 3.2 m, times each tree's scale
CROWN_HEIGHT, CROWN_RADIUS = 5.5, 3.2


def _union(parts):
    return unary_union([Polygon(p["o"], p["i"]).buffer(0) for p in parts]) if parts else Polygon()


def _building_shadows(footprints, sx, sy):
    """Shadow of each building on flat ground: convex hull of footprint + footprint pushed away from the sun."""
    shapes = []
    for poly, h in footprints:
        pts = list(poly.exterior.coords)
        shapes.append(MultiPoint(pts + [(x + sx * h, y + sy * h) for x, y in pts]).convex_hull)
    return unary_union(shapes)


def _tree_shadows(trees, sx, sy, alt):
    """Each crown's shadow: a circle offset away from the sun, stretched along the sun direction."""
    theta = math.atan2(sy, sx)                 # direction the shadows point
    stretch = 1 / math.sin(alt)
    shapes = []
    for x, y, s in trees:
        cx, cy = x + sx * CROWN_HEIGHT * s, y + sy * CROWN_HEIGHT * s
        c = Point(cx, cy).buffer(CROWN_RADIUS * s, quad_segs=3)
        c = rotate(c, -theta, origin=(cx, cy), use_radians=True)
        c = scale(c, xfact=stretch, yfact=1, origin=(cx, cy))
        shapes.append(rotate(c, theta, origin=(cx, cy), use_radians=True))
    return unary_union(shapes) if shapes else Polygon()


def build(area):
    load = lambda name: json.loads((area.site_dir / name).read_text())
    city, ground, trees = load("buildings.json"), load("ground.json"), load("trees.json")

    lon, lat = area.origin
    tz = ZoneInfo(opt(area, "shade.timezone", "Asia/Kolkata"))
    year = opt(area, "shade.year", 2026)
    dates = opt(area, "shade.dates", ["06-15", "12-15"])
    hours = opt(area, "shade.hours", list(range(7, 19)))

    roads = _union(ground["roads"])
    if roads.is_empty:
        raise SystemExit("no roads in ground.json, so nothing to measure shade on")
    footprints = [(Polygon(b["p"]), b["h"]) for b in city["buildings"] if len(b["p"]) >= 3]

    results = {}
    print(f"  {'date':6s} {'hour':>4s} {'sun':>5s} {'buildings':>10s} {'+ trees':>8s}")
    for md in dates:
        month, day = map(int, md.split("-"))
        rows = []
        for hour in hours:
            when = datetime(year, month, day, hour, 0, tzinfo=tz)
            pos = get_position(when, lng=lon, lat=lat)
            alt, az = pos["altitude"], pos["azimuth"]   # azimuth: from south, positive towards west
            row = {"hour": hour, "sun_altitude_deg": round(math.degrees(alt), 1),
                   "sun_bearing_deg": round((math.degrees(az) + 180) % 360, 1)}
            if alt < math.radians(3):                   # sun too low or below the horizon
                row.update(buildings=None, buildings_and_trees=None)
                rows.append(row)
                print(f"  {md:6s} {hour:4d} {row['sun_altitude_deg']:4.0f}° {'(sun too low)':>19s}")
                continue

            # shadow offset per metre of height, pointing away from the sun (x = east, y = north)
            k = 1 / math.tan(alt)
            sx, sy = math.sin(az) * k, math.cos(az) * k

            b_shadow = _building_shadows(footprints, sx, sy)
            t_shadow = _tree_shadows(trees["trees"], sx, sy, alt)
            row["buildings"] = round(roads.intersection(b_shadow).area / roads.area, 3)
            row["buildings_and_trees"] = round(roads.intersection(unary_union([b_shadow, t_shadow])).area / roads.area, 3)
            rows.append(row)
            print(f"  {md:6s} {hour:4d} {row['sun_altitude_deg']:4.0f}° {row['buildings']:10.0%} {row['buildings_and_trees']:8.0%}")
        results[md] = rows

    out = {
        "area": area.name,
        "measure": "share of road surface in shadow",
        "timezone": str(tz),
        "year": year,
        "notes": [
            "flat ground; building shadows use each footprint's convex hull (slight overestimate for L/U shapes)",
            "trees are placed by the pipeline, not real canopy: treat 'buildings_and_trees' as indicative",
        ],
        "dates": results,
    }
    kb = write_json(area.site_dir / "shade.json", out)
    print(f"  -> shade.json ({kb:.0f} KB)")