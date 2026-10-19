#!/usr/bin/env python3
"""
my task was to compare Suzzana's list (container, test_type) with the ReproFlake test list
and keep the rows that match:

Inputs
  list file   agentflake_144.xlsx (or the same list as .csv).
              Needs the columns: container, test_type
  test list   test_config_proj_mod.csv from github.com/suzzy777/reproduce-flaky
              (same rows as ReproFlake's test_config.csv, plus the columns
              project and flaky_commit). Needs the column: result_container

A row of the list "matches" when its container text is EXACTLY equal to a
result_container value of the test list.

Output
  <prefix>_matched.csv     the matched rows with ALL test list columns
  <prefix>_unmatched.csv   the rows of the list that were not found

no extra packages are needed (.xlsx files are read with the standard library).

Usage
  python compare_containers.py agentflake_144.xlsx test_config_proj_mod.csv matched_144
"""
import csv, collections, sys, zipfile
import xml.etree.ElementTree as ET

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def col_index(ref):
    """'B12' -> 1 (zero based column index)."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def read_xlsx(path):
    """Rows of the first sheet as a list of dicts (first row = header)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall('m:si', NS):
                shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
        sheet_name = sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'))[0]
        root = ET.fromstring(z.read(sheet_name))
        table = []
        for row in root.iter('{%s}row' % NS['m']):
            cells = {}
            for c in row.findall('m:c', NS):
                t = c.get('t')
                if t == 'inlineStr':
                    val = ''.join(x.text or '' for x in c.iter('{%s}t' % NS['m']))
                else:
                    v = c.find('m:v', NS)
                    val = '' if v is None or v.text is None else v.text
                    if t == 's' and val != '':
                        val = shared[int(val)]
                cells[col_index(c.get('r'))] = val.strip()
            if cells:
                table.append([cells.get(i, '') for i in range(max(cells) + 1)])
    header = table[0]
    return [dict(zip(header, r + [''] * (len(header) - len(r)))) for r in table[1:] if any(r)]


def read_table(path):
    if path.lower().endswith('.xlsx'):
        return read_xlsx(path)
    return list(csv.DictReader(open(path, encoding='utf-8-sig', errors='ignore')))


if len(sys.argv) != 4:
    sys.exit(__doc__)
list_path, cfg_path, prefix = sys.argv[1:4]

sheet = read_table(list_path)
cfg_rows = read_table(cfg_path)
for need, rows, name in (('container', sheet, list_path), ('result_container', cfg_rows, cfg_path)):
    if not rows or need not in rows[0]:
        sys.exit(f'ERROR: column "{need}" not found in {name}')
cfg = {r['result_container']: r for r in cfg_rows}

matched, unmatched = [], []
for s in sheet:
    r = cfg.get(s['container'])
    if r is None:
        unmatched.append(s)
    else:
        matched.append({'sheet_test_type': s['test_type'], **r})

print('list rows:', len(sheet), '| test list rows:', len(cfg_rows), '| unique result_container:', len(cfg))
print('matched:', len(matched), 'of', len(sheet))
by_total = collections.Counter(s['test_type'] for s in sheet)
by_match = collections.Counter(m['sheet_test_type'] for m in matched)
for t in by_total:
    print(f'  {t}: {by_match[t]} / {by_total[t]}')
bad = [m['result_container'] for m in matched if m['sheet_test_type'].lower() != m['test_type'].lower()]
print('type disagreements between the list and the test list:', len(bad))
print('unique zips among the matches:', len({m['zip'] for m in matched}))

if matched:
    with open(prefix + '_matched.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(matched[0].keys()))
        w.writeheader()
        w.writerows(matched)
with open(prefix + '_unmatched.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['container', 'test_type'])
    w.writeheader()
    w.writerows(unmatched)
print('wrote', prefix + '_matched.csv and', prefix + '_unmatched.csv')
