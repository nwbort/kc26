# Kepler Challenge finish estimator

Static pages that supporters use to answer "when will they finish?" on race
day. They type in checkpoint times from live tracking, and the page projects
the remaining checkpoints and the finish from how comparable 2025 runners went.

- `index.html`: Kepler Challenge 60 km (race 1), Nick, 6:00am start
- `grunt.html`: Luxmore Grunt 27 km (race 2), Nicole, 7:00am start

The two pages install as one home-screen app (iOS Safari: Share → Add to
Home Screen; Android Chrome: menu → Install app), switched with the tabs at
the top. It reopens on whichever race was viewed last. Once opened with
signal, it keeps working offline, which matters on the track.

Both are gun starts: in 2025 every runner's time was measured from the gun
(run time = race time, time of day = start + race time), so a race time on
tracking converts straight to a clock time.

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
| `index.html`, `grunt.html`, `style.css`, `app.js` | The pages (no build step, no dependencies) |
| `app.webmanifest`, `sw.js`, `icons/` | Home-screen install and offline cache (`scripts/make_icons.py` redraws the icons). Bump `CACHE` in `sw.js` if you add files |
| `model.js` | Estimation maths (pure JS, also runs in node) |
| `config.js`, `grunt-config.js` | **Edit me:** name, bib, goal, start time, band, checkpoint names (Kepler, Grunt) |
| `data/results-2025.json`, `data/grunt-2025.json` | 2025 splits used by the model (Kepler, Grunt) |
| `scripts/build_data.py` | Converts `splits.csv` into the JSON the pages load |
| `scrape.py`, `parse.py`, `results/`, `splits.csv` | Scraper and raw 2025 Kepler results (below) |
| `grunt/` | Raw 2025 Grunt results, same layout |

## Rebuilding the data

```sh
python3 scripts/build_data.py splits.csv                  # Kepler
python3 scripts/build_data.py --grunt grunt/splits.csv    # Grunt
```

This writes `data/results-2025.json` (or `data/grunt-2025.json`) (gun/race time at each checkpoint, plus
bib, gender and category; names are dropped). The script also accepts a wide
CSV with one column per checkpoint, or pasted per-athlete split tables; see
its docstring.

## Run locally / deploy

```sh
python3 -m http.server   # then open http://localhost:8000
```

GitHub Pages: Settings → Pages → Deploy from a branch → `main` / `(root)`.

## Scraping the 2025 results

Scrapes individual results for the
[FreshChoice Kepler Challenge 2025](https://www.sportsplits.com/races/freshchoice-kepler-challenge-2025)
from Sportsplits (event 1, individuals 1–499).

Sportsplits sits behind a Cloudflare challenge ("Checking your browser"), so
plain `curl` only gets a 403. As in
[tribunal-tracker](https://github.com/nwbort/tribunal-tracker), the scraper
(formerly run as a GitHub Action) drives a real Chrome under Xvfb with
[nodriver](https://github.com/ultrafunkamsterdam/nodriver) to clear it, then
loads each results page in the same browser session.

### Running it

The scraping GitHub Action has been removed now that the 2025 data is in the
repo (it's in git history if it's ever needed again). Individuals already in
`results/` are skipped, so a run that stops part way can be resumed. A
"Too Many Requests" page is retried after a minute, and left for the next run
if it persists.

Locally: `pip install -r requirements.txt`, then

```sh
xvfb-run -a python scrape.py --start 1 --end 499                 # Kepler, bibs 1-499
xvfb-run -a python scrape.py --event 2 --out grunt --discover    # Grunt
```

The number in a results URL is the bib. `--discover` reads the bibs off the
event's results pages (`events/2`, `events/2?page=2`, ...; names read
"LEE GRIEVE (#767)") and fetches only those, skipping DNS. `python parse.py`
(or `python parse.py grunt`) rebuilds the CSVs from `results/`.

### Output

- `results.csv`: one row per individual: `id, bib, name, status, gun_time,
  place, place_of, gender, gender_place, gender_of, category,
  category_place, category_of` (blank time and places for a DNF).
- `splits.csv`: one row per individual per checkpoint: `id, bib, name,
  gender, category, location, split, run_time, race_time, pos, gender_pos,
  category_pos, speed_kmh, pace, tod`. The splits table's "Male"/"Open"
  style columns are the athlete's own gender and category, so their headers
  go in `gender`/`category` and the positions in `gender_pos`/`category_pos`.
- `results/<n>.json`: the same for one individual (`summary` + `splits`).
  A bib with no results page has `"found": false` and is left out of the
  CSVs.
