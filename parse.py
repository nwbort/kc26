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

Writes results/<n>.json for each page, results.json with them all, and
results.csv with one row per individual and a column per field.

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
            result = {"id": page_number(path), **parse_page(f.read())}
        results.append(result)
        with open(os.path.join(RESULTS_DIR, f"{result['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
        f.write("\n")

    # One row per individual: name (first heading), then every field seen,
    # in the order first seen.
    columns: list[str] = []
    for r in results:
        for k in r["fields"]:
            if k not in columns:
                columns.append(k)
    with open("results.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", *columns])
        for r in results:
            name = r["headings"][0]["text"] if r["headings"] else ""
            w.writerow([r["id"], name, *(r["fields"].get(c, "") for c in columns)])

    print(f"Parsed {len(results)} page(s) into {RESULTS_DIR}/, results.json, results.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
