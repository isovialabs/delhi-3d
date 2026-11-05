import json
from pathlib import Path

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point, box
from shapely.ops import unary_union

BBOX = (77.205, 28.622, 77.228, 28.641)   # same pilot area: min_lon, min_lat, max_lon, max_lat
ORIGIN_LONLAT = (77.2167, 28.6315)         # same origin as the buildings
UTM = "EPSG:32643"
OUT = Path("web3d/ground.json")

area = box(*BBOX)
area_utm = gpd.GeoSeries([area], crs=4326).to_crs(UTM).iloc[0]
origin = gpd.GeoSeries([Point(ORIGIN_LONLAT)], crs=4326).to_crs(UTM).iloc[0]

# Approximate full road width in metres, by OSM road type
ROAD_WIDTH = {
    "motorway": 16, "trunk": 16, "primary": 14, "secondary": 12, "tertiary": 10,
    "residential": 7, "unclassified": 7, "service": 5, "living_street": 5, "pedestrian": 5,
}

def road_width(hw):
    if isinstance(hw, list):
        hw = hw[0]
    return ROAD_WIDTH.get(str(hw).replace("_link", ""))

# --- Roads: lines -> widened polygons, merged into one surface
roads = ox.features_from_polygon(area, tags={"highway": True})
roads = roads[roads.geom_type.isin(["LineString", "MultiLineString"])].to_crs(UTM)
roads["w"] = roads["highway"].apply(road_width)
roads = roads.dropna(subset=["w"])                # drop footpaths, tracks, etc.
road_surface = unary_union([g.buffer(w / 2) for g, w in zip(roads.geometry, roads["w"])])
road_surface = road_surface.intersection(area_utm)

# --- Green spaces: parks, gardens, lawns (includes CP's central park)
green = ox.features_from_polygon(area, tags={
    "leisure": ["park", "garden"],
    "landuse": ["grass", "recreation_ground", "village_green"],
})
green = green[green.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(UTM)
green_surface = unary_union(list(green.geometry)).intersection(area_utm)

# --- Convert to local metres, keeping holes (roundabouts, courtyards)
def to_parts(geom, tol=0.5):
    geom = geom.simplify(tol)
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    ring = lambda r: [[round(x - origin.x, 1), round(y - origin.y, 1)] for x, y in list(r.coords)[:-1]]
    out = []
    for p in polys:
        if p.geom_type != "Polygon" or p.area < 1:
            continue
        out.append({"o": ring(p.exterior), "i": [ring(h) for h in p.interiors]})
    return out

data = {
    "origin": ORIGIN_LONLAT,
    "attribution": "Roads and parks © OpenStreetMap contributors (ODbL)",
    "roads": to_parts(road_surface),
    "green": to_parts(green_surface),
}
OUT.write_text(json.dumps(data, separators=(",", ":")))
print(f"roads: {len(data['roads'])} pieces, green: {len(data['green'])} pieces -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
print(f"road area: {road_surface.area / 1e6:.2f} km2, green area: {green_surface.area / 1e6:.2f} km2")