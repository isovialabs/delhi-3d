import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import Polygon
from suncalc import get_position

from .common import opt, origin_xy, write_json

CLASSES = ["major", "local", "walkways"]


def _shadow(H, res, alt, az, max_dist=300):
    """True where a cell is in shadow: something towards the sun rises above the sun's line."""
    rows, cols = H.shape
    tan_a = math.tan(alt)
    reach = min(max_dist, float(H.max()) / tan_a)
    di, dj = math.cos(az), -math.sin(az)        # one metre towards the sun, in (row, col) steps
    pad = int(math.ceil(reach / res)) + 2
    P = np.pad(H, pad)
    shade = np.zeros(H.shape, bool)
    d = res
    while d <= reach:
        oi, oj = int(round(di * d / res)), int(round(dj * d / res))
        shifted = P[pad + oi: pad + oi + rows, pad + oj: pad + oj + cols]
        shade |= shifted > H + d * tan_a
        d += res
    return shade


def build(area):
    res = opt(area, "raster.resolution_m", 4)
    meta = json.loads((area.data_dir / f"height_{res}m.json").read_text())
    H = np.load(area.data_dir / f"height_{res}m.npy")
    H = np.where(H >= opt(area, "buildings.min_measured_height_m", 2.5), H, 0).astype(np.float32)
    building = H > 0

    # Street surfaces (from OSM) burned onto the same grid
    ground = json.loads((area.site_dir / "ground.json").read_text())
    ox, oy = origin_xy(area)
    transform = from_origin(meta["minx"] - ox, meta["maxy"] - oy, res, res)

    def to_mask(parts):
        geoms = [g for g in (Polygon(p["o"], p["i"]).buffer(0) for p in parts) if not g.is_empty]
        if not geoms:
            return np.zeros(H.shape, bool)
        return rasterize([(g, 1) for g in geoms], out_shape=H.shape, transform=transform).astype(bool)

    classes = ground.get("classes", {})
    masks = {"major": to_mask(classes.get("major", [])),
             "local": to_mask(classes.get("local", [])),
             "walkways": to_mask(ground.get("walkways", []))}

    print(f"  grid {H.shape[1]} x {H.shape[0]} at {res} m | building cells {building.mean():.0%}")
    for c in CLASSES:
        m = masks[c]
        overlap = (m & building).sum() / max(m.sum(), 1)
        masks[c] = m & ~building               # a street cell the grid says is a building isn't open street
        print(f"  {c:9s} street cells {m.sum():7d} | {overlap:4.0%} overlap a building in the grid (removed)")

    tz = ZoneInfo(opt(area, "shade.timezone", "Asia/Kolkata"))
    year = opt(area, "shade.year", 2026)
    lon, lat = area.origin
    results = {}
    print(f"  {'date':6s} {'hour':>4s} {'sun':>4s} | buildings only: " + " ".join(f"{c:>9s}" for c in CLASSES))
    for md in opt(area, "shade.dates", ["06-15", "12-15"]):
        month, day = map(int, md.split("-"))
        rows = []
        for hour in opt(area, "shade.hours", list(range(7, 19))):
            pos = get_position(datetime(year, month, day, hour, 0, tzinfo=tz), lng=lon, lat=lat)
            alt, az = pos["altitude"], pos["azimuth"]
            row = {"hour": hour, "sun_altitude_deg": round(math.degrees(alt), 1)}
            if alt < math.radians(3):
                row["buildings"] = None
                rows.append(row)
                print(f"  {md:6s} {hour:4d} {row['sun_altitude_deg']:3.0f}° | sun too low")
                continue
            sh = _shadow(H, res, alt, az)
            row["buildings"] = {c: round(float(sh[masks[c]].mean()), 3) if masks[c].any() else None for c in CLASSES}
            rows.append(row)
            print(f"  {md:6s} {hour:4d} {row['sun_altitude_deg']:3.0f}° |                 "
                  + " ".join(f"{row['buildings'][c]:9.0%}" if row["buildings"][c] is not None else "        -"
                             for c in CLASSES))
        results[md] = rows

    out = {
        "area": area.name,
        "measure": "share of open street cells in shadow, computed on the building height grid",
        "grid_resolution_m": res,
        "building_cell_share": round(float(building.mean()), 3),
        "notes": [
            "heights from the Open Buildings 2.5D Temporal raster, so buildings without a detected footprint also cast shadows",
            f"{res} m cells: streets narrower than about {res} m may be lost into neighbouring building cells",
            "buildings only: no trees yet",
        ],
        "dates": results,
    }
    kb = write_json(area.site_dir / "shade_raster.json", out)
    print(f"  -> shade_raster.json ({kb:.0f} KB)")