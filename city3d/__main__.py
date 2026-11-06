import argparse
import time

from . import buildings, ground, report, shade, trees
from .common import load_area

STEPS = {"buildings": None, "ground": ground.build, "trees": trees.build,
         "shade": shade.build, "report": report.build}
DEFAULT = "buildings,ground,trees,report"


def main():
    parser = argparse.ArgumentParser(prog="city3d", description="Build 3D city sites from open data.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build a site from an area config")
    b.add_argument("config", help="e.g. areas/connaught-place.yaml")
    b.add_argument("--steps", default=DEFAULT,
                   help=f"comma-separated, from {list(STEPS)}; default {DEFAULT} (shade only when asked)")
    b.add_argument("--refresh", action="store_true", help="re-download building data instead of using the cache")
    args = parser.parse_args()

    area = load_area(args.config)
    print(f"{area.name}: bbox {area.bbox}, projection {area.crs}")
    for step in args.steps.split(","):
        if step not in STEPS:
            raise SystemExit(f"unknown step {step!r}; choose from {list(STEPS)}")
        t0 = time.time()
        print(f"[{step}]")
        if step == "buildings":
            buildings.build(area, refresh=args.refresh)
        else:
            STEPS[step](area)
        print(f"  done in {time.time() - t0:.0f}s")
    print(f"\nsite ready: sites/{area.name}/  ->  open /web3d/?area={area.name}")


if __name__ == "__main__":
    main()