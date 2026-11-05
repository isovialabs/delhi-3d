import json
import random
import sys

sys.path.insert(0, ".")                     # so we can import the city3d engine
import geopandas as gpd
import pandas as pd

from city3d.buildings import railway_land
from city3d.common import load_area

name = sys.argv[1]
area = load_area(f"areas/{name}.yaml")
d = gpd.read_file(f"data/{name}/buildings_raw_open_buildings_c065.geojson")
d["confidence"] = pd.to_numeric(d["confidence"], errors="coerce")
h75 = pd.to_numeric(d["h_p75"], errors="coerce").fillna(0)

rail = railway_land(area)
on_rail = d.geometry.representative_point().within(rail) if rail is not None else pd.Series(False, index=d.index)
added = (d["confidence"] < 0.75) & ~on_rail
groups = [("kept", d[added & (h75 >= 2.5)], 50), ("dropped", d[added & (h75 < 2.5)], 25)]

rng = random.Random(7)
samples = []
for group, g, n in groups:
    for idx in rng.sample(list(g.index), min(n, len(g))):
        samples.append({"id": int(idx), "group": group,
                        "conf": round(float(g.at[idx, "confidence"]), 3),
                        "geom": g.geometry.loc[idx].__geo_interface__})
rng.shuffle(samples)                         # blind: groups are mixed together

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Label check: __AREA__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html,body{margin:0;height:100%;font-family:system-ui,sans-serif;background:#111;color:#eee}
#map{position:absolute;inset:0}
#panel{position:absolute;z-index:1000;left:12px;top:12px;background:rgba(20,20,20,.92);padding:12px 14px;border-radius:8px;max-width:330px}
button{font:inherit;margin:4px 4px 0 0;padding:8px 10px;border-radius:6px;border:1px solid #555;background:#2a2a2a;color:#eee;cursor:pointer}
button:hover{background:#3a3a3a}
.small{font-size:12px;color:#aaa;margin-top:4px}
</style></head><body>
<div id="map"></div>
<div id="panel">
  <div><b>__AREA__</b> · <span id="pos"></span></div>
  <div class="small">Is the red outline a building? Keys 1–4, Backspace to go back.</div>
  <div id="buttons">
    <button data-l="real">1 · Real building</button>
    <button data-l="fragment">2 · Part of a bigger building</button>
    <button data-l="false">3 · Not a building</button>
    <button data-l="unsure">4 · Unsure</button>
    <button id="back">← Back</button>
  </div>
  <div id="done" style="display:none"><p>All done.</p><button id="dl">Download results CSV</button></div>
</div>
<script>
const SAMPLES = __SAMPLES__;
const KEY = 'labels-__AREA__';
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {} };

const map = L.map('map');
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  { maxNativeZoom: 19, maxZoom: 21, attribution: 'Imagery © Esri' }).addTo(map);
let layer = null;
let i = SAMPLES.findIndex((s) => !(s.id in labels));
if (i < 0) i = SAMPLES.length;

function show() {
  document.getElementById('pos').textContent = `${Math.min(i + 1, SAMPLES.length)} / ${SAMPLES.length}`;
  const done = i >= SAMPLES.length;
  document.getElementById('buttons').style.display = done ? 'none' : 'block';
  document.getElementById('done').style.display = done ? 'block' : 'none';
  if (layer) map.removeLayer(layer);
  if (done) return;
  layer = L.geoJSON(SAMPLES[i].geom, { style: { color: '#ff2a2a', weight: 3, fill: false } }).addTo(map);
  map.fitBounds(layer.getBounds(), { maxZoom: 20, padding: [120, 120] });
}
function label(l) {
  if (i >= SAMPLES.length) return;
  labels[SAMPLES[i].id] = l; save(); i++; show();
}
function back() { if (i > 0) { i--; show(); } }
document.querySelectorAll('button[data-l]').forEach((b) => (b.onclick = () => label(b.dataset.l)));
document.getElementById('back').onclick = back;
addEventListener('keydown', (e) => {
  const m = { 1: 'real', 2: 'fragment', 3: 'false', 4: 'unsure' }[e.key];
  if (m) label(m);
  if (e.key === 'Backspace') back();
});
document.getElementById('dl').onclick = () => {
  const rows = ['id,group,confidence,label', ...SAMPLES.map((s) => `${s.id},${s.group},${s.conf},${labels[s.id] || ''}`)];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' }));
  a.download = 'labels___AREA__.csv';
  a.click();
};
show();
</script></body></html>"""

out = f"data/label_{name}.html"
with open(out, "w", encoding="utf-8") as f:
    f.write(HTML.replace("__AREA__", name).replace("__SAMPLES__", json.dumps(samples)))
print(f"{len(samples)} samples ({sum(s['group'] == 'kept' for s in samples)} kept, "
      f"{sum(s['group'] == 'dropped' for s in samples)} dropped) -> {out}")