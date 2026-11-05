import sys
import geopandas as gpd

area = sys.argv[1] if len(sys.argv) > 1 else "chandni-chowk"
d = gpd.read_file(f"data/{area}/buildings_raw_open_buildings_c065.geojson")
d["area_m2"] = d.to_crs(d.estimate_utm_crs()).area
d["has_height"] = d["h_p75"].fillna(0) >= 2.5

old = d[d.confidence >= 0.75]
new = d[d.confidence < 0.75]
print(f"{area}: kept at 0.75: {len(old)}  |  added by 0.65: {len(new)}")
print(f"  median area:     kept {old.area_m2.median():.0f} m2, added {new.area_m2.median():.0f} m2")
print(f"  measured height: kept {old.has_height.mean():.0%}, added {new.has_height.mean():.0%}")

# Outlines over satellite imagery: white = kept, orange = added, red = 50 random added ones to check
style = lambda c, w: {"color": c, "weight": w, "fillOpacity": 0}
m = old.explore(tiles="Esri.WorldImagery", style_kwds=style("white", 1))
new.explore(m=m, style_kwds=style("orange", 1))
new.sample(50, random_state=1).explore(m=m, style_kwds=style("red", 3))
m.save(f"data/check_{area}.html")
print(f"  open data/check_{area}.html")