# kc26

Scrapes individual results for the
[FreshChoice Kepler Challenge 2025](https://www.sportsplits.com/races/freshchoice-kepler-challenge-2025)
from Sportsplits (event 1, individuals 1–499).

Sportsplits sits behind a Cloudflare challenge ("Checking your browser"), so
plain `curl` only gets a 403. As in
[tribunal-tracker](https://github.com/nwbort/tribunal-tracker), the GitHub
Action drives a real Chrome under Xvfb with
[nodriver](https://github.com/ultrafunkamsterdam/nodriver) to clear it, then
loads each results page in the same browser session.

## Running it

The [Scrape results](.github/workflows/scrape.yml) workflow runs when the
scraper changes, or by hand from the Actions tab (Run workflow), where the
race, event, range of individuals and a "re-fetch" option can be set.
Individuals already in `results/` are skipped, so a run that stops part way
can be resumed by running it again.

Locally: `pip install -r requirements.txt`, then
`xvfb-run -a python scrape.py --start 1 --end 499`. `python parse.py`
rebuilds the CSVs from `results/`.

## Output

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
