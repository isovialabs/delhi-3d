import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from .common import area_polygon, opt, origin_xy, ring_to_local, write_json


def fetch_open_buildings(area, min_conf):
    """Google Open Buildings footprints + 2.5D Temporal heights, via Earth Engine."""
    import ee
    ee.Initialize(project=opt(area, "earth_engine_project", "isovia-delhi3d"))
    aoi = ee.Geometry.Rectangle(list(area.bbox))
    footprints = (
        ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
        .filterBounds(aoi)
        .filter(ee.Filter.gte("confidence", min_conf))
    )
    temporal = ee.ImageCollection("GOOGLE/Research/open-buildings-temporal/v1").filterBounds(aoi)
    latest = temporal.aggregate_max("inference_time_epoch_s")
    height = temporal.filter(ee.Filter.eq("inference_time_epoch_s", latest)).mosaic().select("building_height")
    reducer = ee.Reducer.median().combine(ee.Reducer.percentile([75]), sharedInputs=True)
    fc = height.reduceRegions(collection=footprints, reducer=reducer, scale=4).select(
        ["confidence", "median", "p75"], ["confidence", "h_median", "h_p75"]
    )
    gdf = ee.data.computeFeatures({"expression": fc, "fileFormat": "GEOPANDAS_GEODATAFRAME"})
    return gdf.set_crs("EPSG:4326")


# Add more sources here later (e.g. Overture Maps for the US and Europe)
SOURCES = {"open_buildings": fetch_open_buildings}


def railway_land(area):
    """OSM railway land as one shape (lon/lat), or None."""
    import osmnx
    try:
        rail = osmnx.features_from_polygon(area_polygon(area), tags={"landuse": "railway"})
    except Exception:
        return None
    rail = rail[rail.geom_type.isin(["Polygon", "MultiPolygon"])]
    return rail.union_all() if len(rail) else None


def build(area, refresh=False):
    min_conf = opt(area, "buildings.min_confidence", 0.75)
    source = opt(area, "buildings.source", "open_buildings")

    # Cache name records the settings, so a config change never reuses stale data
    raw = area.data_dir / f"buildings_raw_{source}_c{round(min_conf * 100):03d}.geojson"
    if raw.exists() and not refresh:
        gdf = gpd.read_file(raw)
        print(f"  using cached {raw.name}  (add --refresh to re-download)")
    else:
        if source not in SOURCES:
            raise SystemExit(f"unknown building source: {source}")
        gdf = SOURCES[source](area, min_conf)
        if gdf.empty:
            raise SystemExit("no buildings found: check the area is covered by this source")
        gdf.to_file(raw, driver="GeoJSON")

    # Railway mask: drop low-confidence detections on railway land (platforms, trains)
    gdf["confidence"] = pd.to_numeric(gdf["confidence"], errors="coerce")
    mask_below = opt(area, "buildings.railway_mask_below_confidence", 0.75)
    if mask_below:
        rail = railway_land(area)
        if rail is not None:
            on_rail = gdf.geometry.representative_point().within(rail) & (gdf["confidence"] < mask_below)
            print(f"  railway mask: dropped {int(on_rail.sum())} low-confidence detections")
            gdf = gdf[~on_rail]

    # Low-confidence footprints must be confirmed by the height data
    confirm_below = opt(area, "buildings.require_height_below_confidence", None)
    if confirm_below:
        h75 = pd.to_numeric(gdf["h_p75"], errors="coerce").fillna(0)
        unconfirmed = (gdf["confidence"] < confirm_below) & (h75 < opt(area, "buildings.min_measured_height_m", 2.5))
        print(f"  height check: dropped {int(unconfirmed.sum())} low-confidence detections with no height signal")
        gdf = gdf[~unconfirmed]

    # Heights: 75th percentile; anything too low gets a flagged default
    for col in ("h_median", "h_p75"):
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce")
    gdf["height_m"] = gdf["h_p75"]
    gdf["estimated"] = gdf["height_m"].isna() | (gdf["height_m"] < opt(area, "buildings.min_measured_height_m", 2.5))
    gdf.loc[gdf["estimated"], "height_m"] = opt(area, "buildings.default_height_m", 3.0)

    tower = opt(area, "buildings.tower_height_m", 30)
    mid = opt(area, "buildings.mid_height_m", 10)

    gdf = gdf.to_crs(area.crs).explode(index_parts=False)
    gdf = gdf[gdf.geometry.geom_type == "Polygon"]
    ox, oy = origin_xy(area)

    out = []
    for _, row in gdf.iterrows():
        poly = Polygon(row.geometry.exterior).simplify(0.3)
        if poly.is_empty or poly.geom_type != "Polygon" or poly.area < 4:
            continue
        poly = orient(poly, sign=1.0)                  # counter-clockwise, so walls face outward
        h = float(row["height_m"])
        if row["estimated"]:
            kind = "estimated"
        elif h > tower:
            kind = "tower"
        elif h >= mid:
            kind = "mid"
        else:
            kind = "low"
        out.append({
            "h": round(h, 1),
            "f": max(1, round(h / 3.2)),
            "c": kind,
            "p": ring_to_local(poly.exterior.coords, ox, oy),
        })

    kb = write_json(area.site_dir / "buildings.json", {"origin": area.origin, "crs": area.crs, "buildings": out})
    print(f"  {len(out)} buildings -> buildings.json ({kb:.0f} KB)")