import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from shapely.affinity import rotate, scale, translate
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep
from suncalc import get_position

from .common import opt, write_json

# Same tree shape as the 3D viewer: crown centre 5.5 m up, radius 3.2 m, times each tree's scale
CROWN_HEIGHT, CROWN_RADIUS = 5.5, 3.2
CLASSES = ["major", "local", "walkways"]


def _union(parts):
    return unary_union([Polygon(p["o"], p["i"]).buffer(0) for p in parts]) if parts else Polygon()


def _polys(buildings):
    out = []
    for b in buildings:
        if len(b["p"]) < 3:
            continue
        p = Polygon(b["p"]).buffer(0)
        if not p.is_empty and p.geom_type == "Polygon":
            out.append((p, b["h"]))
    return out


def _hull_shadows(footprints, sx, sy):
    """Fast: convex hull of footprint + footprint pushed away from the sun (fine for simple shapes)."""
    shapes = []
    for poly, h in footprints:
        pts = list(poly.exterior.coords)
        shapes.append(MultiPoint(pts + [(x + sx * h, y + sy * h) for x, y in pts]).convex_hull)
    return unary_union(shapes)


def _exact_shadows(footprints, sx, sy):
    """Exact shadow of an extruded polygon: itself, its moved copy, and every edge swept between them."""
    parts = []
    for poly, h in footprints:
        dx, dy = sx * h, sy * h
        parts += [poly, translate(poly, dx, dy)]
        ring = list(poly.exterior.coords)
        for (x1, y1), (x2, y2) in zip(ring[:-1], ring[1:]):
            q = Polygon([(x1, y1), (x2, y2), (x2 + dx, y2 + dy), (x1 + dx, y1 + dy)])
            if q.area > 1e-6:
                parts.append(q)
    return unary_union(parts) if parts else Polygon()


def _tree_shadows(trees, sx, sy, alt):
    """Each crown's shadow: a circle offset away from the sun, stretched along the sun direction."""
    theta = math.atan2(sy, sx)
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

    # Buildings: detected footprints, plus gap-filling buildings from the height grid if available
    footprints = _polys(city["buildings"])
    fill_path = area.site_dir / "fill.json"
    fillers = _polys(json.loads(fill_path.read_text())["buildings"]) \
        if fill_path.exists() and opt(area, "shade.use_fill", True) else []
    all_buildings = unary_union([p for p, _ in footprints + fillers])
    print(f"  buildings: {len(footprints)} footprints + {len(fillers)} fillers")

    # Street surfaces from OSM, trimmed so no street runs under a building
    classes = ground.get("classes", {})
    raw = {"major": _union(classes.get("major", [])),
           "local": _union(classes.get("local", [])),
           "walkways": _union(ground.get("walkways", []))}
    surfaces = {}
    for c, s in raw.items():
        if s.is_empty:
            continue
        trimmed = s.difference(all_buildings)
        print(f"  {c:9s} street surface {s.area:9.0f} m2 | {1 - trimmed.area / s.area:4.0%} lay under a building (removed)")
        if not trimmed.is_empty:
            surfaces[c] = trimmed

    # Placed trees can't stand on a filler building
    filler_zone = prep(unary_union([p for p, _ in fillers])) if fillers else None
    tree_list = [t for t in trees["trees"] if not (filler_zone and filler_zone.contains(Point(t[0], t[1])))]
    print(f"  trees: {len(tree_list)} of {len(trees['trees'])} kept (rest stood on filler buildings)")

    tz = ZoneInfo(opt(area, "shade.timezone", "Asia/Kolkata"))
    year = opt(area, "shade.year", 2026)
    lon, lat = area.origin
    frac = lambda shadow: {k: round(s.intersection(shadow).area / s.area, 3) for k, s in surfaces.items()}
    pct = lambda v: f"{v:9.0%}" if v is not None else "        -"
    names = " ".join(f"{c:>9s}" for c in CLASSES)

    results = {}
    print(f"  {'date':6s} {'hour':>4s} {'sun':>4s} | buildings only: {names} | with trees: {names}")
    for md in opt(area, "shade.dates", ["06-15", "12-15"]):
        month, day = map(int, md.split("-"))
        rows = []
        for hour in opt(area, "shade.hours", list(range(7, 19))):
            pos = get_position(datetime(year, month, day, hour, 0, tzinfo=tz), lng=lon, lat=lat)
            alt, az = pos["altitude"], pos["azimuth"]   # azimuth: from south, positive towards west
            row = {"hour": hour, "sun_altitude_deg": round(math.degrees(alt), 1),
                   "sun_bearing_deg": round((math.degrees(az) + 180) % 360, 1)}
            if alt < math.radians(3):
                row.update(buildings=None, buildings_and_trees=None)
                rows.append(row)
                print(f"  {md:6s} {hour:4d} {row['sun_altitude_deg']:3.0f}° | sun too low")
                continue

            # shadow offset per metre of height, pointing away from the sun (x = east, y = north)
            k = 1 / math.tan(alt)
            sx, sy = math.sin(az) * k, math.cos(az) * k
            b_shadow = unary_union([_hull_shadows(footprints, sx, sy), _exact_shadows(fillers, sx, sy)])
            t_shadow = _tree_shadows(tree_list, sx, sy, alt)
            row["buildings"] = frac(b_shadow)
            row["buildings_and_trees"] = frac(unary_union([b_shadow, t_shadow]))
            rows.append(row)
            b, bt = row["buildings"], row["buildings_and_trees"]
            print(f"  {md:6s} {hour:4d} {row['sun_altitude_deg']:3.0f}° |                 "
                  + "".join(pct(b.get(c)) for c in CLASSES) + " |             "
                  + "".join(pct(bt.get(c)) for c in CLASSES))
        results[md] = rows

    out = {
        "area": area.name,
        "measure": "share of each street type's open surface in shadow",
        "buildings": {"footprints": len(footprints), "fillers": len(fillers)},
        "timezone": str(tz),
        "year": year,
        "notes": [
            "flat ground; footprint shadows use convex hulls, filler shadows are exact",
            "filler buildings come from the 4 m height grid: edges about ±2 m",
            "street widths from OSM road type, trimmed where they run under a building",
            "trees are placed by the pipeline, not real canopy: treat 'buildings_and_trees' as indicative",
        ],
        "dates": results,
    }
    kb = write_json(area.site_dir / "shade.json", out)
    print(f"  -> shade.json ({kb:.0f} KB)")