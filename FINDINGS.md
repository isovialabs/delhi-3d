# Findings

## 1. In central Delhi, Open Buildings detections below 0.75 confidence are mostly fragments and clutter

*Isovia Labs · November 2026 · data: Google Open Buildings v3 + 2.5D Temporal*

### Summary
Google Open Buildings is usually filtered at `confidence ≥ 0.75`. We tested whether
lowering the threshold to 0.65 recovers missed buildings in two contrasting areas of
central Delhi. Lowering it doubles to triples the number of detections, but blind
hand-labelling shows that only ~15–20% of the extra detections are separate real
buildings; about half are fragments of existing buildings and about a third are not
buildings at all. This holds in both a dense historic area and a leafy planned one.
A simple height-confirmation rule (accept a low-confidence footprint only if the
height raster shows a structure) is an effective filter: it removed no real buildings
in either sample. **The standard 0.75 threshold remains the right default.**

### Areas
Two 4.74 km² boxes, processed identically with `city3d`.

| | Connaught Place | Chandni Chowk |
|---|---|---|
| Character | planned, colonial ring, offices, leafy bungalow zone | historic walled city, very dense |
| bbox | 77.205, 28.622, 77.228, 28.641 | 77.219, 28.647, 77.242, 28.666 |

### Automated results

| | CP @0.75 | CP @0.65 + checks | CC @0.75 | CC @0.65 + checks |
|---|---|---|---|---|
| Detections | 3,201 | 6,509 | 8,706 | 22,854 |
| Footprint coverage | 17% | 22% | 19% | 33% |

| Extra detections (0.65–0.75) | Connaught Place | Chandni Chowk |
|---|---|---|
| Count | 4,395 | 15,146 |
| Median size, added vs kept | 40 m² vs 126 m² | 34 m² vs 69 m² |
| With height signal, added vs kept | 76% vs 87% | 94% vs 94% |
| Removed by railway mask | 86 | 166 |
| Removed by height check | 997 | 798 |

### Hand-labelled results (blind)
For each area, 50 extra detections the height rule kept and 25 it dropped were
shuffled together and labelled on Esri satellite imagery without knowing the group.
"Unsure" answers (1–2 per group) are excluded. 95% Wilson intervals.

| | CP kept (n=49) | CP dropped (n=24) | CC kept (n=48) | CC dropped (n=24) |
|---|---|---|---|---|
| Separate real building | 14% (7–27%) | 0% (0–14%) | 19% (10–32%) | 0% (0–14%) |
| Part of a bigger building | 51% | 25% | 50% | 21% |
| Not a building | 35% | 75% | 31% | 79% |

### Interpretation
- **The 0.65–0.75 band adds little.** Most extra detections are pieces of buildings
  already detected (one roof split into several adjacent footprints) or not buildings.
  An earlier automated overlap check missed this, because fragments sit *next to*
  existing footprints rather than on top of them.
- **Lowering the threshold inflates building counts and coverage.** The coverage gains
  in the table above are overstated by the false positives and should not be used.
- **No difference between dense and leafy areas** at this sample size, despite the
  areas differing in the automated height-signal statistics.
- **Height confirmation works as a filter**: what it removes is overwhelmingly not
  buildings (75–79%), and it removed no separate real buildings in either sample.

### Limitations
- One labeller; no inter-rater agreement yet. "Separate" vs "part of a bigger
  building" is a genuine judgement call in row housing with shared walls.
- Labelling imagery (Esri) may differ in date from the imagery behind Open Buildings.
- 50 + 25 samples per area gives wide intervals (about ±10–13 points).
- Two areas, one city.

### Next
- Second labeller on the same samples (Cohen's kappa); self-relabel after a delay.
- Test the 0.75–0.80 band the same way: are confident detections also fragmented?
- More area types (unauthorised colony, urban village, planned suburb).

### Reproduce
    python -m city3d build areas/<area>.yaml          # with min_confidence: 0.65
    python scripts/check_confidence.py <area>
    python scripts/make_labeling.py <area>            # label in data/label_<area>.html
    python scripts/score_labels.py results/labels/labels_<area>.csv