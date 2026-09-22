"""Build a static index from actual major agreements, excluding report metadata."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent
OUT_FILE = ROOT / 'data' / 'index.json'
YEAR_RE = re.compile(r'^(\d{4})_year_(\d+)$')
SOURCES = [('deanza', 'De Anza College', 'uc_to_deanza'),
           ('foothill', 'Foothill College', 'uc_to_foothill')]


def decoded(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def pick_latest_year(years):
    return max(years, key=lambda year: tuple(map(int, YEAR_RE.fullmatch(year).groups())), default='')


def build_college(college_id, name, folder):
    root = ROOT / 'data' / folder
    campuses = []
    if root.is_dir():
        for campus_dir in sorted(root.iterdir()):
            if not campus_dir.is_dir():
                continue
            year_map = {}
            institution = {}
            for year_dir in sorted(campus_dir.iterdir()):
                if not year_dir.is_dir() or not YEAR_RE.fullmatch(year_dir.name):
                    continue
                majors = []
                for file in sorted(year_dir.glob('*.json')):
                    payload = json.loads(file.read_text(encoding='utf-8-sig'))
                    result = payload.get('result', payload) if isinstance(payload, dict) else {}
                    if result.get('type') != 'Major' or not isinstance(result.get('articulations'), list):
                        continue
                    sender = decoded(result.get('sendingInstitution'))
                    sender_names = [n.get('name') for n in sender.get('names', [])]
                    if name not in sender_names:
                        raise ValueError(f'{file}: agreement is not from {name}')
                    institution = decoded(result.get('receivingInstitution'))
                    majors.append({'id': file.stem, 'pretty': result.get('name') or file.stem.replace('_', ' '),
                                   'path': file.relative_to(ROOT).as_posix()})
                if majors:
                    year_map[year_dir.name] = sorted(majors, key=lambda major: (major['pretty'].casefold(), major['id']))
            if not year_map:
                continue
            names = institution.get('names') or []
            pretty = max(names, key=lambda item: item.get('fromYear', 0)).get('name') if names else campus_dir.name.replace('_', ' ')
            campuses.append({'id': campus_dir.name, 'code': institution.get('code', '').strip() or campus_dir.name.split('_')[0],
                             'pretty': pretty, 'category': institution.get('category', 'University'),
                             'years': sorted(year_map, reverse=True), 'latestYear': pick_latest_year(year_map), 'yearMap': year_map})
    return {'id': college_id, 'name': name, 'campuses': sorted(campuses, key=lambda campus: campus['pretty'].casefold())}


def main():
    colleges = [build_college(*source) for source in SOURCES]
    if not any(college['campuses'] for college in colleges):
        raise SystemExit('No major agreements found under data/.')
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Keep the original shape for older pages still cached by a browser or CDN.
    legacy_campuses = next(c['campuses'] for c in colleges if c['id'] == 'deanza')
    OUT_FILE.write_text(json.dumps({'schemaVersion': 2, 'colleges': colleges,
                                    'campuses': legacy_campuses}, ensure_ascii=False), encoding='utf-8')
    for college in colleges:
        count = sum(len(majors) for campus in college['campuses'] for majors in campus['yearMap'].values())
        print(f"{college['name']}: {len(college['campuses'])} campuses, {count} major agreements")


if __name__ == '__main__':
    main()
