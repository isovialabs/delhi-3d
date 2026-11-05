# Findings

## 1. The standard confidence threshold undercounts buildings in dense neighbourhoods

*Isovia Labs · November 2026 · data: Google Open Buildings v3 + 2.5D Temporal*

### Summary
Google Open Buildings is usually filtered at `confidence ≥ 0.75`. In Old Delhi
(Chandni Chowk) this threshold discards most of the neighbourhood's buildings:
lowering it to 0.65, with two safeguards, raises the building count 2.6× and
footprint coverage from 19% to 33%. In leafy, low-density Connaught Place the
same change helps far less, and a quarter of the extra detections have no height
signal. A simple rule (accept a low-confidence footprint only if the height data
independently confirms a structure) handles both areas without per-area tuning.

### Areas
Two 4.74 km² boxes in central Delhi, processed identically with the `city3d` pipeline.

| | Connaught Place | Chandni Chowk |
|---|---|---|
| Character | planned, colonial ring, offices, leafy bungalow zone | historic walled city, very dense, narrow lanes |
| bbox | 77.205, 28.622, 77.228, 28.641 | 77.219, 28.647, 77.242, 28.666 |

### Results

| | CP @0.75 | CP @0.65 + checks | CC @0.75 | CC @0.65 + checks |
|---|---|---|---|---|
| Buildings | 3,201 | **6,509** (2.0×) | 8,706 | **22,854** (2.6×) |
| Buildings / km² | 676 | 1,374 | 1,838 | 4,825 |
| Footprint coverage | 17% | **22%** | 19% | **33%** |
| Median height (measured) | 8.7 m | 7.9 m | 7.5 m | 7.1 m |

What the extra detections (confidence 0.65–0.75) look like:

| | Connaught Place | Chandni Chowk |
|---|---|---|
| Added detections | 4,395 | 15,146 |
| Median size, added vs kept | 40 m² vs 126 m² | 34 m² vs 69 m² |
| With a height signal, added vs kept | **76%** vs 87% | **94%** vs 94% |
| Removed by railway mask | 86 | 166 |
| Removed by height check | 997 (23%) | 798 (5%) |
| Heavy overlap with a kept building | not measured | 20 (0.1%) |

### Interpretation
- **In Chandni Chowk the extra detections are real buildings the model was unsure
  about.** They are small (≈6 × 6 m), almost never duplicate an existing footprint,
  and carry height signal as often as confident detections. The 0.75 threshold
  was removing a large part of the actual city.
- **In Connaught Place the extras are weaker.** They are 3× smaller than the kept
  buildings and a quarter show no height, consistent with sheds, kiosks,
  structures under tree canopy, or false positives.
- **Implication:** a single global threshold is biased against the densest,
  smallest-grained neighbourhoods, often the informal and historic ones.

### Method
1. Download footprints at `confidence ≥ 0.65`; height = 75th percentile of the
   2.5D Temporal height raster (4 m) inside each footprint.
2. **Railway mask:** drop detections with confidence < 0.75 whose representative
   point lies on OSM `landuse=railway` (platform canopies, carriages).
3. **Height confirmation:** drop detections with confidence < 0.75 whose
   75th-percentile height is < 2.5 m.
4. Coverage = area of the union of footprints (overlaps counted once) ÷ box area.

### Limitations
- **No manual precision check yet.** Height confirmation is indirect evidence;
  a hand-labelled sample is the next step.
- **The height raster is itself a model output,** so the two signals are not
  fully independent (both derive from satellite imagery).
- **Height confirmation raises the "measured" share by construction**; that
  share is not an independent quality score after the rule is applied.
- The 0.65, 0.75 and 2.5 m cut-offs were chosen, not tuned.
- Two areas only, one city.
- The 0.75 baseline coverage summed footprint areas; overlap analysis showed
  duplicates are negligible, so the comparison holds.

### Next
- Hand-label 50 random added detections per area to estimate precision.
- Add contrasting areas: a planned colony (e.g. Dwarka), an unauthorised colony
  (e.g. Sangam Vihar), an urban village.
- Compare against OSM building footprints where they are well mapped.

### Reproduce
    python -m city3d build areas/connaught-place.yaml
    python -m city3d build areas/chandni-chowk.yaml
    python scripts/check_confidence.py connaught-place
    python scripts/check_confidence.py chandni-chowk