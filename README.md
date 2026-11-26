# Kepler Challenge finish estimator

A static page that supporters use to answer "when will they finish?" on race
day. They type in checkpoint times from live tracking, and the page projects
the remaining checkpoints and the finish from how comparable 2025 runners went.

## How the estimate works

1. **Pool:** 2025 finishers in a fixed percentile band of finish time
   (default 10th–75th, set in `config.js`). This excludes the elites and the
   back of the field.
2. **Plan (pre-race):** the median split fractions of pool runners who
   finished near the goal time, scaled to the goal.
3. **Live:** given time `T` at the latest checkpoint `k`, every pool runner's
   later split `j` becomes `T × t_j / t_k`. Runners whose time at `k` was
   close to `T` are weighted more (Gaussian kernel on log time, which widens
   when too few runners match). The page shows the weighted median and the
   25–75% range.

## Files

| File | Purpose |
|---|---|
| `index.html`, `style.css`, `app.js` | The page (no build step, no dependencies) |
| `model.js` | Estimation maths (pure JS, also runs in node) |
| `config.js` | **Edit me:** name, bib, goal, start time, band, checkpoint names |
| `data/results-2025.json` | 2025 splits used by the model |
| `scripts/build_data.py` | Converts an export of 2025 splits into the JSON |
| `scripts/make_demo_data.py` | Synthetic placeholder data (the page shows a "Demo data" banner while it's in use) |

## Loading the real 2025 splits

`scripts/build_data.py` accepts either:

- **Wide CSV/TSV:** one row per athlete. Optional `bib,name,gender,category`
  columns, plus one column per checkpoint whose header contains the distance
  (`RUN 13.8KM`, `13.8km`, ...). Cells are race times (h:mm:ss).
- **Long text:** each athlete's split table as copied from sportsplits,
  preceded by a `## bib | name | gender | category` line. The **Race Time**
  (gun) column is used.

```sh
python3 scripts/build_data.py data/raw/kepler2025.csv
```

The output JSON keeps bib, gender and category, but not names.

## Run locally / deploy

```sh
python3 -m http.server   # then open http://localhost:8000
```

GitHub Pages: Settings → Pages → Deploy from a branch → `main` / `(root)`.
