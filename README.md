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
race, event, range of individuals and a "re-fetch" option can be set. Pages
already saved are skipped, so a run that stops part way can be resumed by
running it again.

Locally: `pip install -r requirements.txt`, then
`xvfb-run -a python scrape.py --start 1 --end 499` and `python parse.py`.

## Output

- `pages/<n>.html`: each individual's results page as rendered (styles,
  SVGs and external scripts removed).
- `results/<n>.json`: what `parse.py` found on the page: `headings`,
  `fields` (label/value pairs such as bib, category, places, finish time),
  `tables` (e.g. the splits) and any `embedded` JSON.
- `results.json`: all of the above in one file.
- `results.csv`: one row per individual, a column per field.

`parse.py` only reads `pages/`, so it can be refined and re-run without
scraping again.
