import json
import re
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import yaml
from shapely.geometry import Point, box


@dataclass
class Area:
    name: str
    bbox: tuple          # (min_lon, min_lat, max_lon, max_lat)
    origin: tuple        # (lon, lat) that becomes (0, 0) in the 3D scene
    crs: str             # local metre-based projection, picked automatically
    cfg: dict

    @property
    def site_dir(self) -> Path:   # built output, committed
        return Path("sites") / self.name

    @property
    def data_dir(self) -> Path:   # raw downloads, git-ignored
        return Path("data") / self.name


def load_area(path) -> Area:
    cfg = yaml.safe_load(Path(path).read_text())
    name = cfg["name"]
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise SystemExit(f"area name must be lowercase letters, digits and dashes: {name!r}")
    bbox = tuple(cfg["bbox"])
    origin = tuple(cfg.get("origin") or ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2))
    # picks the right UTM zone for wherever the area is in the world
    crs = gpd.GeoSeries([box(*bbox)], crs=4326).estimate_utm_crs().to_string()
    area = Area(name, bbox, origin, crs, cfg)
    area.site_dir.mkdir(parents=True, exist_ok=True)
    area.data_dir.mkdir(parents=True, exist_ok=True)
    return area


def opt(area: Area, dotted: str, default):
    """Read a config value like 'trees.seed', falling back to a default."""
    node = area.cfg
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def area_polygon(area: Area, crs=None):
    """The area's bounding box, in lon/lat or in a given projection."""
    g = gpd.GeoSeries([box(*area.bbox)], crs=4326)
    return g.to_crs(crs).iloc[0] if crs else g.iloc[0]


def origin_xy(area: Area):
    o = gpd.GeoSeries([Point(area.origin)], crs=4326).to_crs(area.crs).iloc[0]
    return o.x, o.y


def ring_to_local(coords, ox, oy):
    """Projected ring -> [[x, y], ...] in metres from the origin, without the repeated closing point."""
    return [[round(x - ox, 1), round(y - oy, 1)] for x, y in list(coords)[:-1]]


def write_json(path, obj) -> float:
    Path(path).write_text(json.dumps(obj, separators=(",", ":")))
    return Path(path).stat().st_size / 1024