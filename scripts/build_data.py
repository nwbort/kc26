#!/usr/bin/env python3
"""Convert exported Kepler 2025 splits into data/results-2025.json for the web app.

Accepted inputs (one or more files):

1. Wide CSV/TSV - one row per athlete. Recognised columns (case-insensitive):
     bib, name, gender|sex, category|cat   (all optional)
   plus one column per checkpoint whose header contains the distance, e.g.
   "RUN 13.8KM" or "13.8km" or "Luxmore 13.8 km". Cells are race times
   (h:mm:ss or mm:ss); blank / DNF / "-" = no split.

2. Long CSV - one row per athlete per checkpoint, as written by scrape.py /
   parse.py (splits.csv): columns id, bib, gender, category, location,
   race_time, ... Rows are grouped by id (or bib).

3. Long text - the per-athlete split table as copied from sportsplits,
   each athlete preceded by a header line starting with '##':
     ## 123 | Jane Doe | F | Open
     Location  Split  Run Time  Race Time  Pos  Male  Open  Speed/Pace  TOD
     RUN 5KM   00:28:22  00:28:40  00:28:40  101 ...
   The "Race Time" column (gun time) is used.

Usage: python3 scripts/build_data.py data/raw/splits.csv [more files...]
"""
import csv, json, re, sys, datetime, pathlib

KM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*KM", re.I)


def secs(s):
    s = (s or "").strip()
    if not re.fullmatch(r"\d{1,2}(:\d{1,2}){1,2}(\.\d+)?", s):
        return None
    parts = [float(p) for p in s.split(":")]
    if len(parts) == 2:
        parts = [0] + parts
    h, m, x = parts
    return round(h * 3600 + m * 60 + x)


def norm_gender(s):
    s = (s or "").strip().upper()
    return "F" if s[:1] in ("F", "W") else "M" if s[:1] == "M" else ""


def read_wide(path):
    text = path.read_text(encoding="utf-8-sig")
    dialect = "excel-tab" if text.count("\t") > text.count(",") else "excel"
    rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    out = []
    for r in rows:
        low = {k.strip().lower(): v for k, v in r.items() if k}
        t = {}
        for k, v in r.items():
            m = KM_RE.search(k or "")
            if m:
                t[float(m.group(1))] = secs(v)
        out.append({
            "b": (low.get("bib") or "").strip(),
            "g": norm_gender(low.get("gender") or low.get("sex")),
            "c": (low.get("category") or low.get("cat") or "").strip(),
            "t": t,
        })
    return out


def read_long_csv(path):
    by = {}
    for r in csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()):
        key = r.get("id") or r.get("bib")
        a = by.setdefault(key, {"b": (r.get("bib") or "").strip(),
                                "g": norm_gender(r.get("gender")),
                                "c": (r.get("category") or "").strip(), "t": {}})
        m = KM_RE.search(r.get("location") or "")
        if m:
            a["t"][float(m.group(1))] = secs(r.get("race_time"))
    return list(by.values())


def read_long(path):
    out, cur, race_col = [], None, 3
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("##"):
            f = [x.strip() for x in line[2:].split("|")] + ["", "", "", ""]
            cur = {"b": f[0], "g": norm_gender(f[2]), "c": f[3], "t": {}}
            out.append(cur)
            continue
        cols = [c.strip() for c in re.split(r"\t|\s{2,}", line.strip())]
        if cols and cols[0].lower() == "location":
            race_col = next((i for i, c in enumerate(cols) if c.lower() == "race time"), 3)
            continue
        m = KM_RE.search(cols[0]) if cols else None
        if cur is not None and m and len(cols) > race_col:
            cur["t"][float(m.group(1))] = secs(cols[race_col])
    return out


def main(paths):
    athletes = []
    for p in map(pathlib.Path, paths):
        head = p.read_text(encoding="utf-8-sig")[:4000]
        first = head.splitlines()[0].lower() if head else ""
        if "\n##" in "\n" + head:
            athletes += read_long(p)
        elif "location" in first and "race_time" in first:
            athletes += read_long_csv(p)
        else:
            athletes += read_wide(p)
    kms = sorted({k for a in athletes for k in a["t"]})
    if not kms:
        sys.exit("No checkpoint columns found (headers need a distance like '13.8KM').")
    for a in athletes:
        a["t"] = [a["t"].get(k) for k in kms]
    athletes = [a for a in athletes if any(x is not None for x in a["t"])]
    fin = sum(1 for a in athletes if a["t"][-1] is not None)
    out = {
        "meta": {
            "event": "Kepler Challenge 60km",
            "year": 2025,
            "demo": False,
            "source": "sportsplits.com - FreshChoice Kepler Challenge 2025",
            "generated": datetime.date.today().isoformat(),
            "checkpoints": [{"km": k} for k in kms],
        },
        "athletes": athletes,
    }
    dest = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-2025.json"
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {dest}: {len(athletes)} athletes, {fin} finishers, checkpoints {kms}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
