import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient

SRC = Path("data/pilot_cp.geojson")
OUT = Path("web3d/buildings.json")
ORIGIN_LONLAT = (77.2167, 28.6315)   # centre of Connaught Place
UTM = "EPSG:32643"                    # UTM zone 43N, units in metres

# 1. Reproject to metres
gdf = gpd.read_file(SRC).to_crs(UTM)
gdf = gdf.explode(index_parts=False)              # split any multi-part buildings
gdf = gdf[gdf.geometry.geom_type == "Polygon"]

# 2. Put CP's centre at (0, 0)
origin = gpd.GeoSeries([Point(ORIGIN_LONLAT)], crs="EPSG:4326").to_crs(UTM).iloc[0]
ox, oy = origin.x, origin.y

def classify(h, estimated):
    if estimated:
        return "estimated"
    if h > 25:
        return "tower"
    if h >= 10:
        return "mid"
    return "low"

buildings = []
for _, row in gdf.iterrows():
    # outer ring only, lightly simplified, always counter-clockwise
    poly = Polygon(row.geometry.exterior).simplify(0.3)
    if poly.is_empty or poly.geom_type != "Polygon" or poly.area < 4:
        continue
    poly = orient(poly, sign=1.0)
    pts = list(poly.exterior.coords)[:-1]         # drop repeated closing point

    h = float(row["height_m"])
    est = bool(row["height_estimated"])
    buildings.append({
        "h": round(h, 1),                         # height in metres
        "f": max(1, round(h / 3.2)),              # floors
        "c": classify(h, est),                    # building type
        "p": [[round(x - ox, 1), round(y - oy, 1)] for x, y in pts],  # footprint, metres from origin
    })

# 3. Save
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(
    {"origin": ORIGIN_LONLAT, "units": "metres; x = east, y = north", "buildings": buildings},
    separators=(",", ":"),
))

# 4. Summary
xs = [x for b in buildings for x, _ in b["p"]]
ys = [y for b in buildings for _, y in b["p"]]
print(f"{len(buildings)} buildings -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
print("by type:", dict(Counter(b["c"] for b in buildings)))
print(f"extent: x {min(xs):.0f} to {max(xs):.0f} m, y {min(ys):.0f} to {max(ys):.0f} m")