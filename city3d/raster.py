import json
import math

import numpy as np

from .common import area_polygon, opt


def build(area):
    import ee
    ee.Initialize(project=opt(area, "earth_engine_project", "isovia-delhi3d"))

    res = opt(area, "raster.resolution_m", 4)
    minx, miny, maxx, maxy = area_polygon(area, area.crs).bounds
    w, h = math.ceil((maxx - minx) / res), math.ceil((maxy - miny) / res)

    aoi = ee.Geometry.Rectangle(list(area.bbox))
    col = ee.ImageCollection("GOOGLE/Research/open-buildings-temporal/v1").filterBounds(aoi)
    latest = col.aggregate_max("inference_time_epoch_s")
    img = col.filter(ee.Filter.eq("inference_time_epoch_s", latest)).mosaic() \
             .select("building_height").unmask(0).toFloat()

    arr = ee.data.computePixels({
        "expression": img,
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": w, "height": h},
            "affineTransform": {"scaleX": res, "shearX": 0, "translateX": minx,
                                "shearY": 0, "scaleY": -res, "translateY": maxy},
            "crsCode": area.crs,
        },
    })
    heights = np.asarray(arr["building_height"], dtype=np.float32)   # row 0 = north edge

    np.save(area.data_dir / f"height_{res}m.npy", heights)
    (area.data_dir / f"height_{res}m.json").write_text(json.dumps(
        {"res": res, "minx": minx, "maxy": maxy, "crs": area.crs, "shape": list(heights.shape)}))

    built = (heights >= opt(area, "buildings.min_measured_height_m", 2.5)).mean()
    print(f"  height grid {w} x {h} at {res} m | cells with a building (>= 2.5 m): {built:.0%}"
          f" | max {heights.max():.1f} m -> data/{area.name}/height_{res}m.npy")