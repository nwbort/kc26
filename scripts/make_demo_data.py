#!/usr/bin/env python3
"""Generate SYNTHETIC Kepler-like results so the app can be developed before the
real 2025 splits are exported. Output is flagged `"demo": true` and the web app
shows a banner while it is in use. Delete/replace once real data exists:

    python3 scripts/build_data.py data/raw/<your export>.csv
"""
import json, math, random, datetime, pathlib

random.seed(2025)
KMS = [5, 13.8, 19, 23.6, 28.4, 36.1, 44.6, 50.6, 60]
# cumulative fraction of finish time at each checkpoint, taken from one real
# 2025 split line (7:33:46 finisher)
FRAC = [0.0632, 0.2152, 0.3224, 0.4011, 0.4872, 0.6145, 0.7444, 0.8428, 1.0]
SEG = [FRAC[0]] + [FRAC[i] - FRAC[i - 1] for i in range(1, len(FRAC))]

athletes = []
for bib in range(1, 481):
    g = "M" if random.random() < 0.62 else "F"
    while True:
        F = math.exp(random.gauss(math.log(8.1), 0.17) + (0.05 if g == "F" else 0))
        if 4.3 <= F <= 11.6:
            break
    fade = random.gauss(0.025 * (F - 7.5), 0.04)  # slower runners fade more
    segs = []
    for k, s in enumerate(SEG):
        w = -0.6 if k <= 4 else 1.0
        segs.append(s * math.exp(random.gauss(0, 0.06)) * (1 + fade * w))
    tot = sum(segs)
    t, cum = 0.0, []
    for s in segs:
        t += s / tot * F * 3600
        cum.append(round(t))
    if random.random() < 0.07:  # DNF somewhere mid-course
        stop = random.randint(2, 7)
        cum = cum[:stop] + [None] * (len(cum) - stop)
    cum = [None if (c is not None and i < 8 and random.random() < 0.01) else c
           for i, c in enumerate(cum)]  # the odd missed timing mat
    athletes.append({"b": str(bib), "g": g, "c": "", "t": cum})

out = {
    "meta": {
        "event": "Kepler Challenge 60km",
        "year": 2025,
        "demo": True,
        "source": "SYNTHETIC demo data - not real results",
        "generated": datetime.date.today().isoformat(),
        "checkpoints": [{"km": k} for k in KMS],
    },
    "athletes": athletes,
}
p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-2025.json"
p.write_text(json.dumps(out, separators=(",", ":")))
print(f"wrote {p} ({len(athletes)} athletes, demo)")
