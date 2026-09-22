"""Build the pinned 2025–26 course suggestions from two official PDF exports.

Usage: python tools/build_calgetc.py DEANZA_PDF FOOTHILL_PDF
PDF URLs and dates are preserved in the output. Only approved codes get indexed;
De Anza course titles are enriched from this repository's sending-course records.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DA_SOURCE = 'https://www.csueastbay.edu/aps/cccge2526/de-anza-college-cal-getc-2025-26.pdf'
FH_SOURCE = 'https://fhweb.foothill.edu/articulation/pdf/25-26-FH-calgetc-course-list.pdf'
AREAS = {'1A', '1B', '1C', '2', '3A', '3B', '4', '5A', '5B', '5C', '6'}


def key(code):
    return re.sub(r'\s+', '', code).upper()


def metadata():
    found = defaultdict(Counter)
    for file in (ROOT / 'data/uc_to_deanza').rglob('*.json'):
        obj = json.loads(file.read_text(encoding='utf-8-sig'))
        result = obj.get('result', obj) if isinstance(obj, dict) else {}
        for entry in result.get('articulations', []):
            for group in (entry.get('articulation', {}).get('sendingArticulation') or {}).get('items') or []:
                for course in group.get('items') or []:
                    for c in [course, *(course.get('visibleCrossListedCourses') or [])]:
                        c = c.get('course', c)
                        code = f"{c.get('prefix', '')} {c.get('courseNumber', '')}"
                        if c.get('courseTitle'):
                            found[key(code)][(c['courseTitle'], c.get('minUnits'), c.get('maxUnits'))] += 1
    return {code: values.most_common(1)[0][0] for code, values in found.items()}


def deanza(text, titles):
    sections = {
        '1A': ('Area 1A:', 'ENGL'), '1B': ('Area 1B:', 'COMM'), '1C': ('Area 1C:', 'COMM'),
        '2': ('AREA 2:', 'MATH'), '3A': ('3A – Arts:', 'ARTS'), '3B': ('3B – Humanities:', 'AFAM'),
        '4': ('AREA 4:', 'ADMJ'), '5A': ('5A – Physical Sciences:', 'ASTR'),
        '5B': ('5B – Biological Sciences:', 'ANTH'), '6': ('AREA 6:', 'ADMJ')
    }
    # Verified against underlines on page 2; slash entries require BOTH components.
    lab_codes = {
        'ASTR 4/15L', 'ASTR 10/15L', 'CHEM 1A', 'CHEM 1AH', 'CHEM 1B', 'CHEM 1BH',
        'CHEM 1C', 'CHEM 1CH', 'CHEM 10', 'CHEM 25', 'CHEM 30A', 'CHEM 30B', 'GEOL 10',
        'MET 10/10L', 'MET 10/20L', 'MET 12/20L', 'PHYS 2A', 'PHYS 4A',
        'ANTH 1/1L', 'ANTH 1H/1L', 'BIOL 6A', 'BIOL 6AH', 'BIOL 6B', 'BIOL 6C',
        'BIOL 6CH', 'BIOL 10', 'BIOL 10H', 'BIOL 11', 'BIOL 13', 'BIOL 15', 'BIOL 26',
        'BIOL 40C', 'ESCI 1/1L', 'ESCI 19'
    }
    records = {}
    for area, (marker, first_prefix) in sections.items():
        section = text.split(marker, 1)[1].split('Other Course:', 1)[0]
        start = re.search(r'\b' + re.escape(first_prefix) + r'\s+C?\d', section).start()
        section = re.sub(r'\s+', ' ', section[start:]).strip()
        section = re.sub(r'[\ue000-\uf8ff]', '', section)
        prefix = None
        for token in re.split(r',|\bor\b', section):
            token = token.strip()
            match = re.fullmatch(r'(?P<number>C?\d+[A-Z]*(?:/\d+[A-Z]*)?)[*#]*', token)
            if match:
                number = match['number']
            else:
                match = re.fullmatch(r'(?P<prefix>[A-Z][A-Z/ ]*?)\s*(?P<number>C?\d+[A-Z]*(?:/\d+[A-Z]*)?)[*#]*', token)
                if match:
                    prefix = match['prefix'].strip()
                    number = match['number']
            if not match:
                raise ValueError(f'Unrecognized De Anza entry in {area}: {token!r}')
            if prefix == 'ES':
                prefix = 'E S'
            components = [f'{prefix} {n}' for n in number.split('/')]
            code = ' + '.join(components)
            title_parts = [titles.get(key(part), ('', None, None)) for part in components]
            title = ' + '.join(p[0] or part for part, p in zip(components, title_parts))
            if all(p[1] is not None for p in title_parts):
                minimum = sum(p[1] for p in title_parts)
                maximum = sum(p[2] if p[2] is not None else p[1] for p in title_parts)
            else:
                minimum = maximum = None
            record = records.setdefault(code, {'code': code, 'title': title, 'prefix': prefix,
                'components': components, 'areas': [], 'minUnits': minimum, 'maxUnits': maximum,
                'honors': bool(re.search(r'honors', title, re.I))})
            record['areas'].append(area)
            if f'{prefix} {number}' in lab_codes:
                record['areas'].append('5C')
                lab_codes.remove(f'{prefix} {number}')
            if '*' in token:
                record['limitedCredit'] = True
    if lab_codes:
        raise ValueError(f'Unmatched laboratory codes: {lab_codes}')
    return list(records.values())


def foothill(text):
    pattern = re.compile(r'^\s*([A-Z](?:[A-Z ]*[A-Z])?)\s+(C?\d+[A-Z]*)\s{2,}(.+?)\s{2,}(\d+\.\d+)\s+([1-6][ABC]?)\s+F2025(?:\s+F(\d{4}))?\s*$')
    start = re.compile(r'^\s*[A-Z](?:[A-Z ]*[A-Z])?\s+C?\d+[A-Z]*\s{2,}')
    records = []
    current = None
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            prefix, number, title, units, area, removed = match.groups()
            if removed and int(removed) <= 2025:
                raise ValueError('Course removed during checklist year; manual review required')
            code = f'{prefix} {number}'
            current = {'code': code, 'title': title.strip(), 'prefix': prefix, 'components': [code],
                'areas': [area], 'minUnits': float(units), 'maxUnits': float(units),
                'honors': bool(re.search(r'honors', title, re.I))}
            records.append(current)
        elif start.match(line):
            raise ValueError(f'Unrecognized Foothill course row: {line}')
        elif current:
            for area in re.findall(r'\b([1-6][ABC]?)\s+F2025\b', line):
                if area not in current['areas']:
                    current['areas'].append(area)
            # Two wrapped art-history titles in this export; headers aren't titles.
            if line.strip() in {'Christianity', 'Early Christianity'}:
                current['title'] += ' ' + line.strip()
            cross_list = re.search(r'Same as:\s+([A-Z ]+\s+C?\d+[A-Z]*)', line)
            if cross_list:
                current.setdefault('crossListed', []).append(cross_list[1].strip())
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deanza_pdf', type=Path)
    parser.add_argument('foothill_pdf', type=Path)
    args = parser.parse_args()
    texts = []
    for path in [args.deanza_pdf, args.foothill_pdf]:
        with pymupdf.open(path) as doc:
            text = '\n'.join(page.get_text(sort=True) for page in doc)
        if '2025-2026' not in text:
            raise ValueError(f'{path} is not the expected checklist year')
        texts.append(text)
    colleges = {
        'deanza': {'source': DA_SOURCE, 'sourceDate': '2025-08-04', 'courses': deanza(texts[0], metadata())},
        'foothill': {'source': FH_SOURCE, 'sourceDate': '2025-06-10', 'courses': foothill(texts[1])}
    }
    for name, college in colleges.items():
        counts = Counter(a for c in college['courses'] for a in c['areas'])
        assert set(counts) == AREAS, (name, counts)
        assert len({c['code'] for c in college['courses']}) == len(college['courses'])
        print(name, len(college['courses']), dict(sorted(counts.items())))
    output = {'year': '2025-2026', 'reviewed': '2026-09-22', 'colleges': colleges}
    (ROOT / 'data/calgetc-2025-2026.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
