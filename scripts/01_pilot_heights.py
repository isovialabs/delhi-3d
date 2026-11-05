import ee
import pandas as pd
from pathlib import Path

ee.Initialize(project="isovia-delhi3d")

# Pilot area: Connaught Place, ~2 km x 2 km  [min_lon, min_lat, max_lon, max_lat]
aoi = ee.Geometry.Rectangle([77.205, 28.622, 77.228, 28.641])

# Building footprints, keeping only confident detections
buildings = (
    ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
    .filterBounds(aoi)
    .filter(ee.Filter.gte("confidence", 0.75))
)

# Height raster: most recent year available for this area
temporal = ee.ImageCollection("GOOGLE/Research/open-buildings-temporal/v1").filterBounds(aoi)
latest = temporal.aggregate_max("inference_time_epoch_s")
height = (
    temporal.filter(ee.Filter.eq("inference_time_epoch_s", latest))
    .mosaic()
    .select("building_height")
)

# Median AND 75th percentile of height pixels inside each footprint
reducer = ee.Reducer.median().combine(ee.Reducer.percentile([75]), sharedInputs=True)
with_height = height.reduceRegions(
    collection=buildings, reducer=reducer, scale=4
).select(["confidence", "median", "p75"], ["confidence", "h_median", "h_p75"])

print("buildings found:", buildings.size().getInfo())

gdf = ee.data.computeFeatures({
    "expression": with_height,
    "fileFormat": "GEOPANDAS_GEODATAFRAME",
})
gdf = gdf.set_crs("EPSG:4326")

# Use the 75th percentile; anything still under 2.5 m gets a flagged one-storey default
gdf["h_median"] = pd.to_numeric(gdf["h_median"], errors="coerce")
gdf["h_p75"] = pd.to_numeric(gdf["h_p75"], errors="coerce")
gdf["height_m"] = gdf["h_p75"]
gdf["height_estimated"] = gdf["height_m"].isna() | (gdf["height_m"] < 2.5)
gdf.loc[gdf["height_estimated"], "height_m"] = 3.0

out = Path("data/pilot_cp.geojson")
out.parent.mkdir(exist_ok=True)
gdf.to_file(out, driver="GeoJSON")
print("saved", len(gdf), "buildings to", out)

# Sanity check
print("under 2 m with median:", (gdf["h_median"] < 2).sum())
print("still flagged as estimated (p75 < 2.5 m):", gdf["height_estimated"].sum())
print(gdf["height_m"].describe())

tallest = gdf.sort_values("height_m", ascending=False).head(5)
for _, row in tallest.iterrows():
    c = row.geometry.centroid
    print(f"{row['height_m']:.1f} m at {c.y:.5f}, {c.x:.5f}")