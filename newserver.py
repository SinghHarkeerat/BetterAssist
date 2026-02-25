# newserver.py
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
import json
import os

ROOT = Path(__file__).resolve().parent
def find_uc_to_deanza(root: Path) -> Path:
    # 1) common expected path
    p1 = root / "De Anza files" / "uc_to_deanza"
    if p1.exists() and p1.is_dir():
        return p1

    # 2) search anywhere under project for a folder named uc_to_deanza
    hits = list(root.rglob("uc_to_deanza"))
    hits = [h for h in hits if h.is_dir()]
    if hits:
        # pick the one with the most campus-like subfolders
        hits.sort(key=lambda h: len([x for x in h.iterdir() if x.is_dir()]), reverse=True)
        return hits[0]

    return p1  # fallback (will be missing, but error will show)

DATA_DIR = find_uc_to_deanza(ROOT)

print("DATA_DIR resolved to:", DATA_DIR)
print("Campus folders found:", len([x for x in DATA_DIR.iterdir() if x.is_dir()]) if DATA_DIR.exists() else 0)   # <- your tree root

def safe_relpath(p: Path, base: Path) -> str:
    try:
        return str(p.resolve().relative_to(base.resolve()))
    except Exception:
        return ""

def list_dirs(p: Path):
    if not p.exists() or not p.is_dir():
        return []
    return sorted([x.name for x in p.iterdir() if x.is_dir()])

def list_json_files(p: Path):
    if not p.exists() or not p.is_dir():
        return []
    files = []
    for x in p.iterdir():
        if x.is_file() and x.suffix.lower() == ".json":
            files.append(x.name)
    return sorted(files, key=lambda s: s.lower())

def pick_latest_year(years):
    # expects folders like 2025_year_76
    def key(y):
        try:
            yyyy = int(y[:4])
        except:
            yyyy = -1
        try:
            tail = int(y.split("_year_")[1])
        except:
            tail = -1
        return (yyyy, tail)

    yr = [y for y in years if len(y) >= 4 and y[:4].isdigit() and "_year_" in y]
    if not yr:
        return years[0] if years else ""
    return sorted(yr, key=key, reverse=True)[0]

class Handler(SimpleHTTPRequestHandler):
    # Serve files relative to ROOT (so index.html works)
    def translate_path(self, path):
        # default behavior but rooted at ROOT
        path = urlparse(path).path
        path = unquote(path)
        path = path.split("?", 1)[0].split("#", 1)[0]
        rel = Path(path.lstrip("/"))
        full = (ROOT / rel).resolve()
        # prevent escaping ROOT
        if safe_relpath(full, ROOT) == "":
            return str(ROOT)
        return str(full)

    def _json(self, obj, status=200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/campuses":
            campuses = list_dirs(DATA_DIR)
            # useful display helpers
            out = []
            for folder in campuses:
                code = folder.split("_", 1)[0] if "_" in folder else folder
                pretty = folder.replace("_", " ")
                out.append({"id": folder, "code": code, "pretty": pretty})
            return self._json({"campuses": out})

        if u.path == "/api/campus":
            q = parse_qs(u.query)
            campus = q.get("campus", [""])[0]
            campus = unquote(campus)

            campus_dir = (DATA_DIR / campus)
            if not campus_dir.exists() or not campus_dir.is_dir():
                return self._json({"error": "campus_not_found"}, 404)

            years = list_dirs(campus_dir)
            latest = pick_latest_year(years)
            majors = list_json_files(campus_dir / latest) if latest else []
            # return major *names* without .json for UI
            major_names = [m[:-5] for m in majors]

            return self._json({
                "campus": campus,
                "years": years,
                "latestYear": latest,
                "majors": major_names,
            })

        if u.path == "/api/major":
            q = parse_qs(u.query)
            campus = unquote(q.get("campus", [""])[0])
            year = unquote(q.get("year", [""])[0])
            major = unquote(q.get("major", [""])[0])

            base = DATA_DIR / campus / year
            f = base / f"{major}.json"

            if not f.exists() or not f.is_file():
                return self._json({"error": "major_not_found"}, 404)

            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                return self._json({"error": "bad_json", "message": str(e)}, 500)

            return self._json(obj)

        # otherwise serve static (index.html, script.js, style.css, etc.)
        return super().do_GET()

if __name__ == "__main__":
    os.chdir(ROOT)  # important so static files resolve
    host = "127.0.0.1"
    port = 8000
    print(f"Serving on http://{host}:{port}")
    print(f"Data dir: {DATA_DIR}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()