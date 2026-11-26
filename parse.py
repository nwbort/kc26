#!/usr/bin/env python3
"""
Parse the individual results pages saved by scrape.py (pages/<n>.html).

The page layout couldn't be inspected before the first scrape (Cloudflare
blocks everything but a real browser), so this pulls out whatever structure
the page has rather than relying on particular class names:

- headings (h1-h4), which usually carry the athlete's name;
- fields: label/value pairs from <dl> lists, two-cell table rows and
  <th>/<td> rows (bib, category, places, finish time, ...);
- tables: every other table as headers + rows (the splits);
- embedded: JSON the page carries inline (an Inertia data-page attribute,
  __NEXT_DATA__, <script type="application/json">, Livewire snapshots).

Writes results/<n>.json for each page, results.json with them all,
results.csv with one row per individual (name, bib, status, gun time and
places; see parse_summary), and splits.csv with one row per individual per
checkpoint (see parse_splits).

Usage: parse.py [PAGES_DIR]
"""

import csv
import glob
import json
import os
import re
import sys
from html import unescape
from html.parser import HTMLParser

PAGES_DIR = "pages"
RESULTS_DIR = "results"


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


class PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "template"}
    BLOCK = {"br", "p", "div", "li", "span"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.headings: list[dict] = []
        self.fields: list[tuple[str, str]] = []
        self.tables: list[dict] = []
        self._skip = 0
        self._in_title = False
        self._heading = None  # [tag, text]
        self._table_stack: list[dict] = []
        self._row = None  # list of (tag, text)
        self._cell = None  # [tag, text]
        self._dt = None
        self._dd = None
        self._last_dt = ""

    # --- text routing ---------------------------------------------------
    def _add_text(self, text: str) -> None:
        if self._in_title:
            self.title += text
        if self._heading is not None:
            self._heading[1] += text
        if self._cell is not None:
            self._cell[1] += text
        if self._dt is not None:
            self._dt += text
        if self._dd is not None:
            self._dd += text

    def handle_data(self, data):
        if not self._skip:
            self._add_text(data)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in self.BLOCK:
            self._add_text(" ")
        if tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3", "h4"):
            self._heading = [tag, ""]
        elif tag == "table":
            self._table_stack.append({"headers": [], "rows": []})
        elif tag == "tr" and self._table_stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = [tag, ""]
        elif tag == "dt":
            self._dt = ""
        elif tag == "dd":
            self._dd = ""

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in self.BLOCK:
            self._add_text(" ")
        if tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3", "h4") and self._heading:
            text = clean(self._heading[1])
            if text:
                self.headings.append({"level": self._heading[0], "text": text})
            self._heading = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append((self._cell[0], clean(self._cell[1])))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table_stack:
            self._end_row(self._table_stack[-1], self._row)
            self._row = None
        elif tag == "table" and self._table_stack:
            table = self._table_stack.pop()
            if table["headers"] or table["rows"]:
                self.tables.append(table)
        elif tag == "dt" and self._dt is not None:
            self._last_dt = clean(self._dt)
            self._dt = None
        elif tag == "dd" and self._dd is not None:
            if self._last_dt:
                self.fields.append((self._last_dt, clean(self._dd)))
            self._dd = None

    def _end_row(self, table: dict, row: list[tuple[str, str]]) -> None:
        if not row:
            return
        tags = [t for t, _ in row]
        texts = [x for _, x in row]
        if all(t == "th" for t in tags) and not table["rows"] and not table["headers"]:
            table["headers"] = texts
        elif len(row) == 2 and (tags[0] == "th" or not table["headers"]) and texts[0]:
            # A label/value row: "Bib | 499" or "<th>Category</th><td>M40</td>".
            table.setdefault("pairs", []).append(texts)
            table["rows"].append(texts)
        else:
            table["rows"].append(texts)


EMBEDDED_PATTERNS = [
    ("data-page", re.compile(r'\bdata-page="([^"]*)"', re.S)),
    ("wire:snapshot", re.compile(r'\bwire:snapshot="([^"]*)"', re.S)),
    (
        "__NEXT_DATA__",
        re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S),
    ),
    (
        "application/json",
        re.compile(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', re.S),
    ),
]


def embedded_json(html: str) -> list[dict]:
    found = []
    for kind, pattern in EMBEDDED_PATTERNS:
        for m in pattern.finditer(html):
            try:
                found.append({"kind": kind, "data": json.loads(unescape(m.group(1)))})
            except ValueError:
                pass
    return found


def parse_page(html: str) -> dict:
    p = PageParser()
    p.feed(html)
    p.close()
    fields: dict[str, str] = {}

    def add(label: str, value: str) -> None:
        label = label.rstrip(":").strip()
        if not label:
            return
        key, i = label, 2
        while key in fields and fields[key] != value:
            key, i = f"{label} ({i})", i + 1
        fields[key] = value

    for label, value in p.fields:
        add(label, value)
    tables = []
    for t in p.tables:
        pairs = t.pop("pairs", [])
        # A table made only of label/value rows is a fields table, not data.
        if pairs and len(pairs) == len(t["rows"]) and not t["headers"]:
            for label, value in pairs:
                add(label, value)
        else:
            tables.append(t)
    return {
        "title": clean(p.title),
        "headings": p.headings,
        "fields": fields,
        "tables": tables,
        "embedded": embedded_json(html),
    }


SUMMARY_COLUMNS = [
    "id",
    "bib",
    "name",
    "status",
    "gun_time",
    "place",
    "place_of",
    "gender",
    "gender_place",
    "gender_of",
    "category",
    "category_place",
    "category_of",
]


def _text(html: str) -> str:
    return clean(re.sub(r"<!--.*?-->|<[^>]+>", " ", html, flags=re.S))


def parse_summary(html: str) -> dict:
    """The athlete's header block, which reads (as text):

        BRUCE ADAMS (#1) Finished GUN TIME: 09:56:30
        Place 364 OF 442  Male 255 OF 293  Veteran 50+ 41 OF 50

    A DNF has no time or places: "VAJIN ARMSTRONG (#9) DNF GUN TIME: Place OF
    442 ...". The page title, "(#1) BRUCE ADAMS - FreshChoice Kepler ...", is
    the fallback for the name and bib."""
    s = {c: "" for c in SUMMARY_COLUMNS if c != "id"}
    m = re.search(r"<title[^>]*>\s*\(#([^)]*)\)\s*(.*?)\s+-\s", html, re.S)
    if m:
        s["bib"], s["name"] = clean(m.group(1)), clean(m.group(2))

    start = html.find("g-font-size-30")
    end = html.find("End Overall Statistics", start)
    if start < 0 or end < 0:
        return s
    text = _text(html[html.find(">", start) + 1 : end])

    m = re.match(r"(.*?)\s*\(#([^)]*)\)\s*(.*?)\s*GUN TIME:\s*(\S*)\s*(.*)", text)
    if not m:
        return s
    s["name"], s["bib"], s["status"] = m.group(1), m.group(2), m.group(3)
    s["gun_time"] = m.group(4) if re.fullmatch(r"[\d:.]+", m.group(4)) else ""
    rest = m.group(5) if s["gun_time"] else f"{m.group(4)} {m.group(5)}"

    # "Place 364 OF 442 Male 255 OF 293 Veteran 50+ 41 OF 50": label, place
    # (blank for a DNF), total. Labels can end in digits ("Veteran 50+").
    places = re.findall(r"(.+?)\s+(?:(\d+)\s+)?OF\s+(\d+)\s*", rest)
    if len(places) > 0:
        s["place"], s["place_of"] = places[0][1], places[0][2]
    if len(places) > 1:
        s["gender"], s["gender_place"], s["gender_of"] = places[1]
    if len(places) > 2:
        s["category"], s["category_place"], s["category_of"] = places[2]
    return s


SPLIT_COLUMNS = [
    "id",
    "bib",
    "name",
    "gender",
    "category",
    "location",
    "split",
    "run_time",
    "race_time",
    "pos",
    "gender_pos",
    "category_pos",
    "speed_kmh",
    "pace",
    "tod",
]

# Fixed headers of the splits table, by the column they fill. The two
# columns between "Pos" and "Speed/Pace" are headed by the athlete's own
# gender and category ("Male", "Open"), so those are taken by position.
_SPLIT_HEADERS = {
    "location": "location",
    "split": "split",
    "run time": "run_time",
    "race time": "race_time",
    "pos": "pos",
    "tod": "tod",
}


def _norm(header: str) -> str:
    return re.sub(r"\s+", " ", header).strip().lower()


def find_splits_table(tables: list[dict]) -> dict | None:
    """The table headed Location | Split | Run Time | Race Time | Pos | ..."""
    for t in tables:
        headers = [_norm(h) for h in t["headers"]]
        if "location" in headers and "split" in headers and "pos" in headers:
            return t
    return None


def parse_splits(result: dict) -> list[dict]:
    """The splits table as one dict per checkpoint, keyed by SPLIT_COLUMNS:

        Location  Split     Run Time  Race Time Pos Male Open Speed/Pace    TOD
        RUN 5KM   00:28:22  00:28:40  00:28:40  101 82   48   10.46 / 05:44 06:28:40
    """
    table = find_splits_table(result["tables"])
    if table is None:
        return []
    headers = [_norm(h) for h in table["headers"]]
    pos_i = headers.index("pos")
    speed_i = next((i for i, h in enumerate(headers) if "speed" in h or "pace" in h), None)
    # Columns after Pos and before Speed/Pace: gender, then category.
    extra = list(range(pos_i + 1, speed_i if speed_i is not None else len(headers)))
    extra = [i for i in extra if headers[i] not in _SPLIT_HEADERS]
    gender_i = extra[0] if len(extra) > 0 else None
    category_i = extra[1] if len(extra) > 1 else None

    rows = []
    for cells in table["rows"]:
        if len(cells) != len(headers):
            continue
        row = {c: "" for c in SPLIT_COLUMNS}
        row["id"] = result["id"]
        row["bib"] = result["summary"]["bib"]
        row["name"] = result["summary"]["name"]
        for i, h in enumerate(headers):
            if h in _SPLIT_HEADERS:
                row[_SPLIT_HEADERS[h]] = cells[i]
        if gender_i is not None:
            row["gender"] = table["headers"][gender_i].strip()
            row["gender_pos"] = cells[gender_i]
        if category_i is not None:
            row["category"] = table["headers"][category_i].strip()
            row["category_pos"] = cells[category_i]
        if speed_i is not None:
            speed, _, pace = cells[speed_i].partition("/")
            row["speed_kmh"], row["pace"] = speed.strip(), pace.strip()
        rows.append(row)
    return rows


def page_number(path: str) -> int:
    return int(os.path.splitext(os.path.basename(path))[0])


def main() -> int:
    pages_dir = sys.argv[1] if len(sys.argv) > 1 else PAGES_DIR
    paths = sorted(glob.glob(os.path.join(pages_dir, "*.html")), key=page_number)
    if not paths:
        print(f"No pages in {pages_dir}/")
        return 1
    os.makedirs(RESULTS_DIR, exist_ok=True)

    results = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            html = f.read()
        result = {"id": page_number(path), "summary": parse_summary(html), **parse_page(html)}
        result["splits"] = parse_splits(result)
        results.append(result)
        with open(os.path.join(RESULTS_DIR, f"{result['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
        f.write("\n")

    with open("results.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        w.writeheader()
        w.writerows({"id": r["id"], **r["summary"]} for r in results)

    splits = [row for r in results for row in r["splits"]]
    with open("splits.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SPLIT_COLUMNS)
        w.writeheader()
        w.writerows(splits)
    without = [r["id"] for r in results if not r["splits"]]

    print(f"Parsed {len(results)} page(s) into {RESULTS_DIR}/, results.json, results.csv")
    print(f"Wrote {len(splits)} split(s) to splits.csv")
    if without:
        print(f"No splits table on {len(without)} page(s): {', '.join(map(str, without))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
