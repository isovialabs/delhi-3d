import osmnx
from shapely.ops import unary_union

from .common import area_polygon, opt, origin_xy, ring_to_local, write_json

ROAD_WIDTH_M = {
    "motorway": 16, "trunk": 16, "primary": 14, "secondary": 12, "tertiary": 10,
    "residential": 7, "unclassified": 7, "service": 5, "living_street": 5, "pedestrian": 5,
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
    widths = {**ROAD_WIDTH_M, **opt(area, "ground.road_width_m", {})}

    def width(hw):
        if isinstance(hw, list):
            hw = hw[0]
        return widths.get(str(hw).replace("_link", ""))

    # Roads: centre lines -> widened polygons -> one merged surface
    road_surface = empty
    roads = _features(lonlat, {"highway": True})
    if roads is not None:
        roads = roads[roads.geom_type.isin(["LineString", "MultiLineString"])].to_crs(area.crs)
        roads["w"] = roads["highway"].apply(width)
        roads = roads.dropna(subset=["w"])
        if len(roads):
            road_surface = unary_union([g.buffer(w / 2) for g, w in zip(roads.geometry, roads["w"])]).intersection(clip)

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
        "roads": _to_parts(road_surface, ox, oy),
        "green": _to_parts(green_surface, ox, oy),
    }
    kb = write_json(area.site_dir / "ground.json", data)
    print(f"  roads: {len(data['roads'])} pieces, green: {len(data['green'])} pieces -> ground.json ({kb:.0f} KB)")