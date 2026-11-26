#!/usr/bin/env python3
"""
Parse a Sportsplits individual results page, and build the CSVs.

parse_page() turns a page into:

    {
      "summary": {"bib": "1", "name": "BRUCE ADAMS", "status": "Finished",
                  "gun_time": "09:56:30", "place": "364", "place_of": "442",
                  "gender": "Male", ..., "category": "Veteran 50+", ...},
      "splits": [{"location": "RUN 5KM", "split": "00:32:55", ...}, ...]
    }

scrape.py saves that for each individual as results/<n>.json. Run this file
to rebuild results.csv (one row per individual) and splits.csv (one row per
individual per checkpoint) from results/.
"""

import csv
import glob
import json
import os
import re
import sys
from html import unescape
from html.parser import HTMLParser

RESULTS_DIR = "results"

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
# gender and category ("Male", "Veteran 50+"), so those go by position.
_SPLIT_HEADERS = {
    "location": "location",
    "split": "split",
    "run time": "run_time",
    "race time": "race_time",
    "pos": "pos",
    "tod": "tod",
}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def _text(html: str) -> str:
    return clean(re.sub(r"<!--.*?-->|<[^>]+>", " ", html, flags=re.S))


class TableParser(HTMLParser):
    """Every <table> on the page as {"headers": [...], "rows": [[...], ...]}."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._stack: list[dict] = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append({"headers": [], "rows": []})
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = [tag, ""]

    def handle_data(self, data):
        if self._cell is not None:
            self._cell[1] += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append((self._cell[0], clean(self._cell[1])))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._stack:
            table = self._stack[-1]
            texts = [text for _, text in self._row]
            all_th = all(cell_tag == "th" for cell_tag, _ in self._row)
            if self._row and all_th and not table["headers"]:
                table["headers"] = texts
            elif self._row:
                table["rows"].append(texts)
            self._row = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())


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


def _norm(header: str) -> str:
    return clean(header).lower()


def parse_splits(html: str) -> list[dict]:
    """The splits table as one dict per checkpoint:

        Location  Split     Run Time  Race Time Pos Male Open Speed/Pace    TOD
        RUN 5KM   00:28:22  00:28:40  00:28:40  101 82   48   10.46 / 05:44 06:28:40
    """
    p = TableParser()
    p.feed(html)
    p.close()
    table = next(
        (
            t
            for t in p.tables
            if {"location", "split", "pos"} <= {_norm(h) for h in t["headers"]}
        ),
        None,
    )
    if table is None:
        return []
    headers = [_norm(h) for h in table["headers"]]
    pos_i = headers.index("pos")
    speed_i = next((i for i, h in enumerate(headers) if "speed" in h or "pace" in h), None)
    # Columns after Pos and before Speed/Pace: gender, then category.
    extra = range(pos_i + 1, speed_i if speed_i is not None else len(headers))
    extra = [i for i in extra if headers[i] not in _SPLIT_HEADERS]
    gender_i = extra[0] if len(extra) > 0 else None
    category_i = extra[1] if len(extra) > 1 else None

    rows = []
    for cells in table["rows"]:
        if len(cells) != len(headers):
            continue
        row = {}
        for i, h in enumerate(headers):
            if h in _SPLIT_HEADERS:
                row[_SPLIT_HEADERS[h]] = cells[i]
        if gender_i is not None:
            row["gender"] = clean(table["headers"][gender_i])
            row["gender_pos"] = cells[gender_i]
        if category_i is not None:
            row["category"] = clean(table["headers"][category_i])
            row["category_pos"] = cells[category_i]
        if speed_i is not None:
            speed, _, pace = cells[speed_i].partition("/")
            row["speed_kmh"], row["pace"] = speed.strip(), pace.strip()
        rows.append(row)
    return rows


def parse_page(html: str) -> dict:
    return {"summary": parse_summary(html), "splits": parse_splits(html)}


def result_path(n: int) -> str:
    return os.path.join(RESULTS_DIR, f"{n}.json")


def load_results() -> list[dict]:
    def number(path):
        return int(os.path.splitext(os.path.basename(path))[0])

    results = []
    for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")), key=number):
        with open(path, encoding="utf-8") as f:
            results.append(json.load(f))
    return results


def write_csvs() -> None:
    """results.csv and splits.csv from results/, leaving out bibs that
    don't exist."""
    results = [r for r in load_results() if r.get("found", True)]
    with open("results.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        w.writeheader()
        for r in results:
            w.writerow({"id": r["id"], **r["summary"]})

    n_splits = 0
    with open("splits.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SPLIT_COLUMNS, restval="")
        w.writeheader()
        for r in results:
            for split in r["splits"]:
                w.writerow(
                    {
                        "id": r["id"],
                        "bib": r["summary"]["bib"],
                        "name": r["summary"]["name"],
                        **split,
                    }
                )
                n_splits += 1
    print(f"Wrote {len(results)} individual(s) to results.csv, {n_splits} split(s) to splits.csv")


if __name__ == "__main__":
    write_csvs()
    sys.exit(0)
