#!/usr/bin/env python3
"""
Browser-based scraper for individual results on Sportsplits.

Sportsplits sits behind a Cloudflare managed challenge (its own "Checking
your browser" page), so plain curl only ever gets a 403 and the challenge.
As in tribunal-tracker, we drive a real Chrome via nodriver (headful, under
Xvfb), wait for the challenge to clear, and then load each individual's
results page in the same browser session, which reuses the clearance cookie.

Each page is parsed as it's fetched (see parse.py) and saved as
results/<n>.json; at the end results.csv and splits.csv are rebuilt from
results/. A bib with no results page (it redirects elsewhere, or has no
athlete on it, after a few tries) is saved with "found": false and left out
of the CSVs.

Individuals already in results/ are skipped unless --force is given; bibs
recorded as not found are tried again on every run.

--out sets where results/ and the CSVs go (default: the repo root, for the
Kepler; use --event 2 --out grunt for the Luxmore Grunt).

--discover reads the bibs off the event's results pages (events/<n>,
events/<n>?page=2, ...) and fetches only those, instead of scanning
--start..--end (the URL's number is the bib, and the Grunt's bib range isn't
known up front).

Usage: scrape.py [--race SLUG] [--event N] [--start N] [--end N] [--out DIR]
                 [--discover] [--force]
"""

import argparse
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from shutil import which

import nodriver as uc

import parse

BASE_URL = "https://www.sportsplits.com"
DEFAULT_RACE = "freshchoice-kepler-challenge-2025"
DEFAULT_EVENT = 1

# Titles of Cloudflare's challenge pages. Sportsplits brands its own
# "Checking Your Browser". The title is what we go by: Cloudflare also puts
# its challenge-platform script on the real pages once the challenge clears,
# so markers in the HTML alone would never let a page count as loaded.
CHALLENGE_TITLES = (
    "just a moment",
    "checking your browser",
    "attention required",
    "verifying you are human",
)
# Only consulted for a page with no title at all.
CHALLENGE_MARKERS = (
    "cf_chl_opt",
    "Enable JavaScript and cookies to continue",
    "Verifying you are human",
)

MAX_WAIT_SECONDS = 90
POLL_SECONDS = 0.5
TURNSTILE_CLICK_INTERVAL = 3
CDP_CALL_TIMEOUT_SECONDS = 30
TURNSTILE_FIND_TIMEOUT_SECONDS = 5

# Pause between pages, to be gentle on the site.
DEFAULT_DELAY_SECONDS = 1.0

# How many times to load a page that seems to have no results before
# recording the bib as not found, and the pause between tries.
NOT_FOUND_ATTEMPTS = 3
NOT_FOUND_RETRY_SECONDS = 3

# Give up if this many pages in a row fail: we've probably been blocked.
MAX_CONSECUTIVE_FAILURES = 10

CHROME_ARGS = [
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-service-autorun",
    "--no-default-browser-check",
    "--homepage=about:blank",
    "--no-pings",
    "--password-store=basic",
    "--disable-infobars",
    "--disable-breakpad",
    "--disable-dev-shm-usage",
    "--disable-session-crashed-bubble",
    "--disable-search-engine-choice-screen",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-gpu",
    "--window-size=1920,1080",
    "--no-sandbox",  # CI runs as root
]


def page_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def looks_like_challenge(html: str) -> bool:
    title = page_title(html).lower()
    if title:
        return title.startswith(CHALLENGE_TITLES)
    return any(marker in html for marker in CHALLENGE_MARKERS)


async def with_timeout(coro, what: str, seconds: float = CDP_CALL_TIMEOUT_SECONDS):
    """Await coro, turning a hang into a TimeoutError after seconds."""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(f"{what} did not respond within {seconds}s")


def find_chrome() -> str:
    env = os.environ.get("CHROME_PATH")
    if env and os.path.exists(env):
        return env
    for candidate in (
        "google-chrome",
        "google-chrome-stable",
        "chromium-browser",
        "chromium",
    ):
        path = which(candidate)
        if path:
            return path
    raise FileNotFoundError("Could not find a Chrome/Chromium binary")


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def launch_chrome(chrome_path: str, port: int, user_data_dir: str):
    args = [
        chrome_path,
        *CHROME_ARGS,
        f"--user-data-dir={user_data_dir}",
        "--remote-debugging-host=127.0.0.1",
        f"--remote-debugging-port={port}",
    ]
    # Chrome ignores the proxy environment variables, so pass any HTTPS proxy
    # on explicitly (not needed on GitHub's runners).
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        args.append(f"--proxy-server={proxy}")
    args.append("about:blank")
    print(f"Launching Chrome: {chrome_path} (port {port})", flush=True)
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_for_devtools(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                data = json.load(r)
                print(f"DevTools ready: {data.get('Browser')}", flush=True)
                return True
        except Exception:
            time.sleep(0.5)
    return False


async def try_click_turnstile(tab):
    """Best-effort click of the Cloudflare Turnstile / 'Verify you are human'
    checkbox. Managed challenges often auto-clear, but some render a checkbox
    that must be clicked."""
    for text in ("Verify you are human", "Verify you are a human", "human"):
        try:
            el = await with_timeout(
                tab.find(text, best_match=True, timeout=3),
                "tab.find",
                TURNSTILE_FIND_TIMEOUT_SECONDS,
            )
            if el:
                await with_timeout(el.mouse_click(), "mouse_click")
                print(f"  clicked element matching '{text}'", flush=True)
                return True
        except Exception:
            pass
    try:
        iframe = await with_timeout(
            tab.find("challenges.cloudflare.com", best_match=True, timeout=3),
            "tab.find",
            TURNSTILE_FIND_TIMEOUT_SECONDS,
        )
        if iframe:
            await with_timeout(iframe.mouse_click(), "mouse_click")
            print("  clicked cloudflare iframe", flush=True)
            return True
    except Exception:
        pass
    return False


async def fetch_page(browser, url: str, tab=None):
    """Load url and wait for the Cloudflare challenge to clear. Returns
    (tab, html, where): html is None if the challenge never cleared, and
    where is the URL the tab ended up on if the site redirected elsewhere
    (html is then that page)."""
    print(f"Navigating to {url}", flush=True)
    # Until the navigation commits the tab still shows the previous page. So
    # blank it first: then any loaded http(s) page is where url led, even a
    # redirect to the same page the previous bib redirected to.
    if tab is not None:
        try:
            await with_timeout(tab.get("about:blank"), "tab.get")
        except Exception as e:
            print(f"  could not blank the tab: {e}", flush=True)
    try:
        if tab is None:
            tab = await with_timeout(browser.get(url), "browser.get")
        else:
            await with_timeout(tab.get(url), "tab.get")
    except Exception as e:
        print(f"  navigation failed: {e}", flush=True)
        return tab, None, None

    target = url.split("?")[0].split("#")[0].rstrip("/")
    deadline = time.time() + MAX_WAIT_SECONDS
    next_click = time.time() + TURNSTILE_CLICK_INTERVAL
    attempt = 0
    last_title = None
    while time.time() < deadline:
        attempt += 1
        try:
            # Only take the page once the tab has actually moved and fully
            # loaded. The state, address and HTML are read in one go, so they
            # always describe the same page (nodriver's get_content() can
            # still return the previous page's DOM after a redirect).
            state = await with_timeout(
                tab.evaluate(
                    "JSON.stringify([document.readyState,"
                    " location.origin + location.pathname,"
                    " document.documentElement.outerHTML])"
                ),
                "tab.evaluate",
            )
            ready, href, page_html = json.loads(str(state))
            href = href.rstrip("/")
            arrived = href.startswith("http")
            html = page_html if arrived and ready == "complete" else None
        except Exception as e:
            print(f"  page check failed: {e}", flush=True)
            await tab.sleep(POLL_SECONDS)
            continue

        if html is not None:
            title = page_title(html)
            challenge = looks_like_challenge(html)
            if challenge and title != last_title:
                print(f"  attempt {attempt}: challenge, title={title!r}", flush=True)
                last_title = title
            if not challenge:
                return tab, html, (None if href == target else href)

        if html is not None and time.time() >= next_click:
            await try_click_turnstile(tab)
            next_click = time.time() + TURNSTILE_CLICK_INTERVAL

        await tab.sleep(POLL_SECONDS)

    print(f"WARNING: page did not load or challenge did not clear for {url}", flush=True)
    return tab, None, None


def page_url(race: str, event: int, n: int) -> str:
    return f"{BASE_URL}/races/{race}/events/{event}/results/individuals/{n}"


# Most list pages to read when discovering individuals.
MAX_LIST_PAGES = 60


def listed_ids(html: str, event: int) -> set[int]:
    """Individuals on one page of the event's results list: the numbers in
    its links to individual results (the number is the bib), or failing that
    a "Bib" column."""
    ids = {int(n) for n in re.findall(rf"/events/{event}/results/individuals/(\d+)", html)}
    if ids:
        return ids
    p = parse.TableParser()
    p.feed(html)
    p.close()
    for t in p.tables:
        heads = [parse._norm(h) for h in t["headers"]]
        col = next((i for i, h in enumerate(heads) if h in ("bib", "bib #", "bib no", "#")), None)
        if col is None:
            continue
        for row in t["rows"]:
            m = re.fullmatch(r"#?(\d+)", row[col].strip()) if col < len(row) else None
            if m:
                ids.add(int(m.group(1)))
    return ids


async def discover(browser, tab, race: str, event: int):
    """Bibs listed on the event's results pages (events/<n>, then
    events/<n>?page=2, ...), read until a page adds nobody new, so only
    people who actually ran are fetched. Returns (tab, sorted ids)."""
    base = f"{BASE_URL}/races/{race}/events/{event}"
    ids: set[int] = set()
    for page in range(1, MAX_LIST_PAGES + 1):
        url = base if page == 1 else f"{base}?page={page}"
        html = None
        for _ in range(2):
            tab, html, _where = await fetch_page(browser, url, tab=tab)
            if html is not None:
                break
        if html is None:
            print(f"  list page {page} never loaded; stopping here", flush=True)
            break
        found = listed_ids(html, event)
        new = found - ids
        last = max((int(n) for n in re.findall(r"[?&](?:amp;)?page=(\d+)", html)), default=page)
        print(f"  list page {page}: {len(found)} listed, {len(new)} new (last page link {last})", flush=True)
        if page == 1 and not found:
            text = parse._text(re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S))
            print(f"  nothing listed on {url}; title {page_title(html)!r}; text: {text[:1500]}", flush=True)
        if not new:
            break
        ids |= new
    return tab, sorted(ids)


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def already_found(n: int) -> bool:
    """Whether results/<n>.json holds this individual's results. A bib
    recorded as not found is tried again on every run."""
    try:
        with open(parse.result_path(n), encoding="utf-8") as f:
            return json.load(f).get("found", True)
    except (FileNotFoundError, ValueError):
        return False


async def fetch_result(browser, tab, url: str, n: int):
    """Fetch and parse one individual's page. Returns (tab, result), or
    (tab, None) if the page never got past the challenge.

    A page that looks like it has no results (a redirect, or no athlete on
    it) is loaded again before we believe it: the first look can catch the
    browser part way through moving between pages."""
    result = None
    for attempt in range(1, NOT_FOUND_ATTEMPTS + 1):
        if attempt > 1:
            print(f"  no results for {n}; trying again ({attempt}/{NOT_FOUND_ATTEMPTS})", flush=True)
            await asyncio.sleep(NOT_FOUND_RETRY_SECONDS)
        tab, html, where = await fetch_page(browser, url, tab=tab)
        if html is None:
            return tab, None
        if where:
            # Redirected away. Don't parse what came back: it can still be
            # the previous page's DOM.
            result = {"id": n, "url": url, "found": False, "redirected_to": where}
            continue
        result = {"id": n, "url": url, **parse.parse_page(html)}
        summary = result["summary"]
        result["found"] = bool(summary["name"] or result["splits"])
        if result["found"]:
            return tab, result
        result["title"] = page_title(html)
    return tab, result


async def scrape(args) -> int:
    todo = [n for n in range(args.start, args.end + 1) if args.force or not already_found(n)]
    if not todo and not args.discover:
        print("0 individual(s) to fetch", flush=True)
        parse.write_csvs()
        return 0

    chrome_path = find_chrome()
    port = free_port()
    user_data_dir = tempfile.mkdtemp(prefix="cf-scrape-")
    proc = launch_chrome(chrome_path, port, user_data_dir)
    if not wait_for_devtools(port):
        print("ERROR: Chrome DevTools endpoint never became ready", flush=True)
        proc.terminate()
        return 3

    browser = await uc.start(
        host="127.0.0.1", port=port, browser_executable_path=chrome_path
    )

    failures = []
    consecutive = 0
    tab = None
    try:
        if args.discover:
            tab, ids = await discover(browser, tab, args.race, args.event)
            if not ids:
                print("ERROR: no bibs found on the results pages", flush=True)
                return 4
            print(f"Discovered {len(ids)} bib(s): {ids[0]}..{ids[-1]}", flush=True)
            todo = [n for n in ids if args.force or not already_found(n)]
        print(f"{len(todo)} individual(s) to fetch", flush=True)
        for i, n in enumerate(todo):
            if i:
                await asyncio.sleep(args.delay)
            url = page_url(args.race, args.event, n)
            try:
                tab, result = await fetch_result(browser, tab, url, n)
            except Exception as e:
                print(f"ERROR fetching {url}: {e!r}", flush=True)
                result = None
            if result is None:
                failures.append(n)
                consecutive += 1
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    print(
                        f"ERROR: {consecutive} failures in a row; giving up",
                        flush=True,
                    )
                    break
                continue
            consecutive = 0
            write_json(parse.result_path(n), result)
            if result["found"]:
                summary = result["summary"]
                print(
                    f"  #{summary['bib']} {summary['name']}: {summary['status']}"
                    f" {summary['gun_time']}, {len(result['splits'])} split(s)",
                    flush=True,
                )
            else:
                detail = result.get("redirected_to") or f"title {result.get('title')!r}"
                print(f"  no results for {n} ({detail})", flush=True)
    finally:
        try:
            browser.stop()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass

    parse.write_csvs()
    if failures:
        print(f"Failed ({len(failures)}): {', '.join(map(str, failures))}", flush=True)
        return 2
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--race", default=os.environ.get("RACE") or DEFAULT_RACE)
    p.add_argument("--event", type=int, default=int(os.environ.get("EVENT") or DEFAULT_EVENT))
    p.add_argument("--start", type=int, default=int(os.environ.get("START") or 1))
    p.add_argument("--end", type=int, default=int(os.environ.get("END") or 499))
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    p.add_argument("--out", default=os.environ.get("OUT") or ".")
    p.add_argument(
        "--discover",
        action="store_true",
        default=os.environ.get("DISCOVER") == "true",
        help="fetch only the bibs listed on the event's results pages (else --start..--end)",
    )
    p.add_argument("--force", action="store_true", default=os.environ.get("FORCE") == "true")
    args = p.parse_args()
    parse.OUT_DIR = args.out
    return uc.loop().run_until_complete(scrape(args))


if __name__ == "__main__":
    sys.exit(main())
