import json

import numpy as np
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from scipy import ndimage
from shapely.geometry import Polygon, shape
from shapely.geometry.polygon import orient

from .common import opt, origin_xy, write_json


def build(area):
    res = opt(area, "raster.resolution_m", 4)
    meta_path = area.data_dir / f"height_{res}m.json"
    if not meta_path.exists():
        raise SystemExit("no height grid yet: run with --steps raster first")
    meta = json.loads(meta_path.read_text())
    H = np.load(area.data_dir / f"height_{res}m.npy")
    built = H >= opt(area, "buildings.min_measured_height_m", 2.5)

    city = json.loads((area.site_dir / "buildings.json").read_text())
    ox, oy = origin_xy(area)
    transform = from_origin(meta["minx"] - ox, meta["maxy"] - oy, res, res)

    # Cells touched by any detected footprint are already accounted for
    polys = [p for p in (Polygon(b["p"]).buffer(0) for b in city["buildings"] if len(b["p"]) >= 3) if not p.is_empty]
    covered = rasterize([(p, 1) for p in polys], out_shape=H.shape, transform=transform,
                        all_touched=True).astype(bool)
    gaps = built & ~covered

    # Group touching gap cells into blobs; drop specks smaller than min_cells
    labels, n = ndimage.label(gaps)
    ids = np.arange(1, n + 1)
    sizes = ndimage.sum(gaps, labels, index=ids) if n else np.array([])
    keep = ids[sizes >= opt(area, "fill.min_cells", 2)]
    labels[~np.isin(labels, keep)] = 0
    heights = dict(zip(keep.tolist(), ndimage.median(H, labels, index=keep).tolist())) if len(keep) else {}

    out = []
    for geom, value in shapes(labels.astype(np.int32), mask=labels > 0, transform=transform):
        poly = shape(geom).simplify(0.5)
        if poly.is_empty or poly.geom_type != "Polygon" or poly.area < res * res:
            continue
        poly = orient(Polygon(poly.exterior), sign=1.0)
        h = float(heights[int(value)])
        out.append({"h": round(h, 1), "f": max(1, round(h / 3.2)), "c": "fill",
                    "p": [[round(x, 1), round(y, 1)] for x, y in list(poly.exterior.coords)[:-1]]})

    filled = labels > 0
    print(f"  grid building cells {built.mean():.0%} | touched by footprints {(built & covered).mean():.0%}"
          f" | filled by {len(out)} filler buildings {filled.mean():.0%}"
          f" | specks dropped {(gaps & ~filled).mean():.1%}")

    kb = write_json(area.site_dir / "fill.json", {
        "source": "Open Buildings 2.5D Temporal height grid: built cells not touched by any detected footprint",
        "grid_resolution_m": res,
        "notes": [f"edges follow {res} m grid cells (about ±{res / 2:.0f} m)", "height = median of the blob's cells"],
        "buildings": out,
    })
    print(f"  -> fill.json ({kb:.0f} KB)")