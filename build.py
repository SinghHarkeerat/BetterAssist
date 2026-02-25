from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data" / "uc_to_deanza"
OUT_FILE = ROOT / "data" / "index.json"

YEAR_RE = re.compile(r"^(\d{4})_year_(\d+)$")

def pick_latest_year(years):
    def k(y):
        m = YEAR_RE.match(y)
        if not m:
            return (-1, -1)
        return (int(m.group(1)), int(m.group(2)))
    valid = [y for y in years if YEAR_RE.match(y)]
    if not valid:
        return years[0] if years else ""
    return sorted(valid, key=k, reverse=True)[0]

def main():
    if not DATA_ROOT.exists():
        raise SystemExit(f"Missing folder: {DATA_ROOT}")

    campuses = []
    campus_dirs = sorted([p for p in DATA_ROOT.iterdir() if p.is_dir()], key=lambda p: p.name.lower())

    for cdir in campus_dirs:
        campus_id = cdir.name
        code = campus_id.split("_", 1)[0] if "_" in campus_id else campus_id
        pretty = campus_id.replace("_", " ")

        years = sorted([p.name for p in cdir.iterdir() if p.is_dir()], key=lambda s: s.lower())
        latest = pick_latest_year(years)

        year_map = {}
        for y in years:
            ydir = cdir / y
            majors = []
            for f in ydir.iterdir():
                if f.is_file() and f.suffix.lower() == ".json":
                    major_id = f.stem  # filename without .json
                    majors.append({
                        "id": major_id,                         # exact filename base
                        "pretty": major_id.replace("_", " "),   # display
                        "path": f"data/uc_to_deanza/{campus_id}/{y}/{f.name}"
                    })
            majors.sort(key=lambda m: m["pretty"].lower())
            year_map[y] = majors

        campuses.append({
            "id": campus_id,
            "code": code,
            "pretty": pretty,
            "years": years,
            "latestYear": latest,
            "yearMap": year_map
        })

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({"campuses": campuses}, ensure_ascii=False), encoding="utf-8")

    print("Wrote:", OUT_FILE)
    print("Campuses:", len(campuses))

if __name__ == "__main__":
    main()
    