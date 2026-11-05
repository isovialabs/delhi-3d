import geopandas as gpd

d = gpd.read_file("data/chandni-chowk/buildings_raw.geojson")
d["area_m2"] = d.to_crs("EPSG:32643").area
old = d[d.confidence >= 0.75]
new = d[(d.confidence >= 0.65) & (d.confidence < 0.75)]
print(f"kept at 0.75: {len(old)}  |  added by 0.65: {len(new)}")
print(f"median area: kept {old.area_m2.median():.0f} m2, added {new.area_m2.median():.0f} m2")

# Outlines over satellite imagery: white = kept, orange = added, red = 50 random added ones to check
style = lambda c, w: {"color": c, "weight": w, "fillOpacity": 0}
m = old.explore(tiles="Esri.WorldImagery", style_kwds=style("white", 1))
new.explore(m=m, style_kwds=style("orange", 1))
new.sample(50, random_state=1).explore(m=m, style_kwds=style("red", 3))
m.save("data/check_cc.html")
print("open data/check_cc.html")
# How many added buildings mostly overlap a building that was already kept?
o = old.to_crs("EPSG:32643")
n = new.to_crs("EPSG:32643").reset_index(drop=True)
pairs = gpd.sjoin(n, o[["geometry"]], predicate="intersects", how="inner")
pairs["overlap"] = [
    n.geometry.iloc[i].intersection(o.geometry.loc[j]).area
    for i, j in zip(pairs.index, pairs["index_right"])
]
share = pairs.groupby(level=0)["overlap"].sum().reindex(n.index, fill_value=0) / n.area
print(f"added buildings: {len(n)}")
print(f"  no overlap with kept ones (likely new):  {(share < 0.05).sum()}")
print(f"  partly overlapping (5-30%):               {((share >= 0.05) & (share < 0.3)).sum()}")
print(f"  mostly overlapping (>30%, duplicates):    {(share >= 0.3).sum()}")

union_cov = d[d.confidence >= 0.65].to_crs("EPSG:32643").union_all().area / 4.74e6
print(f"true coverage at 0.65, overlaps counted once: {union_cov:.0%}")