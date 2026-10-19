#!/usr/bin/env python3
"""
Which ReproFlake projects use JUnit 4, JUnit 5 or TestNG?

it reads a CSV that has the columns project, flaky_commit, module 
(for example:
test_config_proj_mod.csv from github.com/suzzy777/reproduce-flaky, 
or the
matched_144_subset.csv made by compare_containers.py).

for every unique (project, flaky_commit, module) it fetches ONLY that module's
src/test folder at the flaky commit from GitHub (partial clone, no history, no
main sources, no Zenodo zips) and counts the .java test files by the imports
they use and then it writes one result row per input row.

Usage:
  python scan_junit.py matched_144_subset.csv junit_scan.csv
  python scan_junit.py matched_144_subset.csv junit_scan.csv --workers 4 --limit 3
"""

import argparse, csv, os, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

J5 = re.compile(r'^\s*import\s+(static\s+)?org\.junit\.jupiter\.', re.M)
J4 = re.compile(r'^\s*import\s+(static\s+)?org\.junit\.(?!jupiter|platform|vintage)', re.M)
TN = re.compile(r'^\s*import\s+(static\s+)?org\.testng\.', re.M)


def longpath(p):
    # Windows refuses paths over 260 characters (some Hadoop test files are that deep).
    # The \\?\ prefix lifts that limit. On Linux/Mac this does nothing.
    if os.name == 'nt':
        p = os.path.abspath(p)
        return p if p.startswith('\\\\?\\') else '\\\\?\\' + p
    return p


def run(cmd, cwd, timeout):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def scan(key):
    project, sha, module = key
    test_path = 'src/test' if module in ('.', '') else module.strip('/') + '/src/test'
    work = tempfile.mkdtemp(prefix='scanjunit_')
    res = dict(test_java=0, junit4=0, junit5=0, testng=0, note='')
    try:
        steps = [
            ['git', 'init', '-q'],
            ['git', 'remote', 'add', 'origin', project.rstrip('/') + '.git'],
            ['git', 'sparse-checkout', 'set', '--cone', test_path],
            ['git', 'fetch', '-q', '--depth', '1', '--filter=blob:none', 'origin', sha],
            ['git', 'checkout', '-q', 'FETCH_HEAD'],
        ]
        for s in steps:
            r = run(s, work, 900)
            if r.returncode != 0:
                res['note'] = 'git failed: ' + ' '.join(s[:3]) + ' | ' + r.stderr.strip()[:120]
                return key, res
        root = longpath(os.path.join(work, test_path))
        if not os.path.isdir(root):
            res['note'] = 'no ' + test_path + ' folder at this commit'
            return key, res
        for dp, _, files in os.walk(root):
            for f in files:
                if f.endswith('.java'):
                    res['test_java'] += 1
                    text = open(longpath(os.path.join(dp, f)), encoding='utf-8', errors='ignore').read()
                    res['junit5'] += bool(J5.search(text))
                    res['junit4'] += bool(J4.search(text))
                    res['testng'] += bool(TN.search(text))
        return key, res
    except Exception as e:
        res['note'] = 'error: ' + str(e)[:150]
        return key, res
    finally:
        shutil.rmtree(work, ignore_errors=True)


def verdict(r):
    if r['note']:
        return 'unknown'
    if r['test_java'] == 0:
        return 'no java tests'
    j4, j5, tn = r['junit4'], r['junit5'], r['testng']
    if j5 and not j4 and not tn:
        return 'junit5 only'
    if j4 and not j5 and not tn:
        return 'junit4 only'
    if tn and not j4 and not j5:
        return 'testng only'
    if j4 or j5 or tn:
        return 'mixed'
    return 'no junit/testng imports'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_csv')
    ap.add_argument('output_csv')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=0, help='only scan the first N unique combos')
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.input_csv, encoding='utf-8')))
    keys = []
    for r in rows:
        k = (r['project'], r['flaky_commit'], r['module'])
        if k not in keys:
            keys.append(k)
    if a.limit:
        keys = keys[:a.limit]
    print(len(keys), 'unique (project, commit, module) combos to scan', file=sys.stderr)

    results = {}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, (k, res) in enumerate(ex.map(scan, keys), 1):
            results[k] = res
            print(f'[{i}/{len(keys)}] {k[0].split("github.com/")[-1]} {k[1][:7]} {k[2]} -> {verdict(res)} {res}', file=sys.stderr)

    fields = list(rows[0].keys()) + ['test_java_files', 'junit4_files', 'junit5_files', 'testng_files', 'verdict', 'note']
    with open(a.output_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            k = (r['project'], r['flaky_commit'], r['module'])
            if k not in results:
                continue
            x = results[k]
            w.writerow({**r, 'test_java_files': x['test_java'], 'junit4_files': x['junit4'],
                        'junit5_files': x['junit5'], 'testng_files': x['testng'],
                        'verdict': verdict(x), 'note': x['note']})
    print('wrote', a.output_csv, file=sys.stderr)


if __name__ == '__main__':
    main()
