import osmnx
from shapely.ops import unary_union

from .common import area_polygon, opt, origin_xy, ring_to_local, write_json

# OSM highway types grouped into classes, with approximate full width in metres
CLASSES = {
    "major": {"motorway": 16, "trunk": 16, "primary": 14, "secondary": 12, "tertiary": 10},
    "local": {"residential": 7, "unclassified": 7, "living_street": 5, "service": 5},
    "walkways": {"pedestrian": 5, "footway": 2.5, "path": 2.5, "steps": 2},
}
GREEN_TAGS = {
    "leisure": ["park", "garden"],
    "landuse": ["grass", "recreation_ground", "village_green"],
}


def _features(polygon, tags):
    try:
        return osmnx.features_from_polygon(polygon, tags=tags)
    except Exception as e:                       # osmnx raises when nothing matches
        print(f"  no OSM features for {list(tags)}: {e.__class__.__name__}")
        return None


def _to_parts(geom, ox, oy, tol=0.5):
    if geom.is_empty:
        return []
    geom = geom.simplify(tol)
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    return [
        {"o": ring_to_local(p.exterior.coords, ox, oy),
         "i": [ring_to_local(h.coords, ox, oy) for h in p.interiors]}
        for p in polys
        if p.geom_type == "Polygon" and p.area >= 1
    ]


def build(area):
    lonlat = area_polygon(area)
    clip = area_polygon(area, area.crs)
    empty = clip.buffer(-1e9)

    # per-area width overrides, e.g. ground: {road_width_m: {footway: 3}}
    overrides = opt(area, "ground.road_width_m", {})
    widths = {c: {k: overrides.get(k, w) for k, w in types.items()} for c, types in CLASSES.items()}

    def classify(hw):
        if isinstance(hw, list):
            hw = hw[0]
        hw = str(hw).replace("_link", "")
        for cls, types in widths.items():
            if hw in types:
                return cls, types[hw]
        return None, None

    # Roads: centre lines -> widened polygons -> one surface per class
    surfaces = {c: empty for c in CLASSES}
    roads = _features(lonlat, {"highway": True})
    if roads is not None:
        roads = roads[roads.geom_type.isin(["LineString", "MultiLineString"])].to_crs(area.crs)
        cw = roads["highway"].apply(classify)
        roads["cls"] = [c for c, _ in cw]
        roads["w"] = [w for _, w in cw]
        roads = roads[roads["cls"].notna()]
        for cls in CLASSES:
            sub = roads[roads["cls"] == cls]
            if len(sub):
                surfaces[cls] = unary_union([g.buffer(w / 2) for g, w in zip(sub.geometry, sub["w"])]).intersection(clip)

    # Make the classes not overlap: major wins over local, vehicle roads win over walkways
    surfaces["local"] = surfaces["local"].difference(surfaces["major"])
    vehicle = unary_union([surfaces["major"], surfaces["local"]])
    surfaces["walkways"] = surfaces["walkways"].difference(vehicle)

    # Green spaces
    green_surface = empty
    green = _features(lonlat, opt(area, "ground.green_tags", GREEN_TAGS))
    if green is not None:
        green = green[green.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(area.crs)
        if len(green):
            green_surface = unary_union(list(green.geometry)).intersection(clip)

    ox, oy = origin_xy(area)
    data = {
        "origin": area.origin,
        "attribution": "Roads and parks © OpenStreetMap contributors (ODbL)",
        "roads": _to_parts(vehicle, ox, oy),                     # all vehicle roads (for drawing)
        "walkways": _to_parts(surfaces["walkways"], ox, oy),
        "green": _to_parts(green_surface, ox, oy),
        "classes": {c: _to_parts(surfaces[c], ox, oy) for c in ("major", "local")},
    }
    kb = write_json(area.site_dir / "ground.json", data)
    m2 = clip.area
    print("  " + " | ".join(f"{c} {surfaces[c].area / m2:.1%}" for c in CLASSES)
          + f" | green {green_surface.area / m2:.1%} -> ground.json ({kb:.0f} KB)")