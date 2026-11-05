import geopandas as gpd

d = gpd.read_file("data/pilot_cp.geojson")
d["area_m2"] = d.to_crs("EPSG:32643").area   # UTM 43N, metres

low = d[d.height_m < 2]
rest = d[d.height_m >= 2]
print("median area, low buildings :", round(low.area_m2.median()), "m2")
print("median area, other buildings:", round(rest.area_m2.median()), "m2")
print("low buildings under 30 m2  :", (low.area_m2 < 30).sum())
print("median confidence, low vs rest:", round(low.confidence.median(), 2), round(rest.confidence.median(), 2))