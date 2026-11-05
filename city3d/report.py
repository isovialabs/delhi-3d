import json
from collections import Counter
from datetime import date

from shapely.geometry import Polygon

from .common import area_polygon, opt

SOURCE_CREDITS = {
    "open_buildings": "Google Open Buildings v3 + 2.5D Temporal (CC BY 4.0)",
}


def _pct(values, q):
    v = sorted(values)
    return round(v[int(q * (len(v) - 1))], 1) if v else None


def _area(parts):
    return sum(Polygon(p["o"], p["i"]).buffer(0).area for p in parts)


def build(area):
    load = lambda name: json.loads((area.site_dir / name).read_text())
    city, ground, trees = load("buildings.json"), load("ground.json"), load("trees.json")

    m2 = area_polygon(area, area.crs).area
    km2 = m2 / 1e6
    blds = city["buildings"]
    measured = [b["h"] for b in blds if b["c"] != "estimated"]
    footprint = sum(Polygon(b["p"]).buffer(0).area for b in blds if len(b["p"]) >= 3)
    source = opt(area, "buildings.source", "open_buildings")

    report = {
        "area": area.name,
        "title": area.cfg.get("title", area.name),
        "generated": date.today().isoformat(),
        "bbox": list(area.bbox),
        "projection": area.crs,
        "area_km2": round(km2, 3),
        "buildings": {
            "count": len(blds),
            "per_km2": round(len(blds) / km2),
            "by_type": dict(Counter(b["c"] for b in blds)),
            "measured_height_share": round(len(measured) / len(blds), 3) if blds else 0,
            "height_m": {"median": _pct(measured, 0.5), "p90": _pct(measured, 0.9),
                         "max": max(measured, default=None)},
            "footprint_coverage": round(footprint / m2, 3),
        },
        "ground": {
            "road_share": round(_area(ground["roads"]) / m2, 3),
            "green_share": round(_area(ground["green"]) / m2, 3),
        },
        "trees": {"count": len(trees["trees"]), "per_km2": round(len(trees["trees"]) / km2)},
        "sources": {
            "buildings": SOURCE_CREDITS.get(source, source),
            "ground": "OpenStreetMap contributors (ODbL)",
        },
    }
    (area.site_dir / "report.json").write_text(json.dumps(report, indent=2))

    b = report["buildings"]
    print(f"  {km2:.2f} km2 | {b['count']} buildings ({b['per_km2']}/km2) | "
          f"{b['measured_height_share']:.0%} measured | median {b['height_m']['median']} m, max {b['height_m']['max']} m")
    print(f"  footprint {b['footprint_coverage']:.0%} | roads {report['ground']['road_share']:.0%} | "
          f"green {report['ground']['green_share']:.0%} | {report['trees']['count']} trees -> report.json")