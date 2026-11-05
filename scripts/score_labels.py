import math
import sys

import pandas as pd


def wilson(k, n, z=1.96):
    """95% confidence interval for a proportion."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


for path in sys.argv[1:]:
    df = pd.read_csv(path)
    print(path)
    for group, sub in df.groupby("group"):
        unsure = (sub["label"] == "unsure").sum() + sub["label"].isna().sum()
        sub = sub[sub["label"].isin(["real", "fragment", "false"])]
        n = len(sub)
        real = (sub["label"] == "real").sum()
        building = sub["label"].isin(["real", "fragment"]).sum()
        lo, hi = wilson(real, n)
        print(f"  {group:8s} n={n:3d} (+{unsure} unsure) | real building {real / n:.0%} (95% CI {lo:.0%}-{hi:.0%})"
              f" | part of a building {(building - real) / n:.0%} | not a building {(sub['label'] == 'false').mean():.0%}")