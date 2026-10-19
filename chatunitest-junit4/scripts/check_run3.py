"""
Reads a ChatUniTest history folder (the one with class*/method*/attempt*/records.json)
and prints, for every round:
  - whether the model returned code and whether it had a compile/run error
  - which JUnit flavour the code uses:  jupiter = JUnit 5 imports,  RunWith(Mockito = JUnit 4 runner,
    org.junit.Test = JUnit 4 import
  - which JUnit version the prompt asked for
then the most common compile errors.

Usage:  python check_run3.py <history folder>
It only reads files. It changes nothing and uses no network.
"""
import sys, glob, os, json, re, collections

root = sys.argv[1]
files = sorted(glob.glob(os.path.join(root, '**', 'records.json'), recursive=True))
if not files:
    sys.exit('no records.json found under ' + root)

errs = collections.Counter()
rounds = with_err = no_code = 0
print('attempt  round  code  error  jupiter  RunWith(Mockito  org.junit.Test  prompt-says')
for f in files:
    attempt = os.path.basename(os.path.dirname(f))
    for r in json.load(open(f, encoding='utf-8')):
        rounds += 1
        code = r.get('code') or ''
        prompt = json.dumps(r.get('prompt'))
        says = 'JUnit 4' if re.search(r'JUnit 4', prompt, re.I) else ('JUnit 5' if re.search(r'JUnit 5', prompt, re.I) else '?')
        has_err = bool(r.get('errorMsg'))
        if not r.get('hasCode'):
            no_code += 1
        if has_err:
            with_err += 1
            for m in r['errorMsg']['errorMessage']:
                m = re.sub(r'^Error in \S+: line \d+ : ', '', m)
                p = [x.strip() for x in m.split('\n')]
                errs[p[0] + (' | ' + p[1] if len(p) > 1 and p[1].startswith('symbol') else '')] += 1
        print('%-8s %-6s %-5s %-6s %-8s %-16s %-14s %s' % (
            attempt, r.get('round'), 'yes' if r.get('hasCode') else 'NO',
            'yes' if has_err else 'no',
            'yes' if 'org.junit.jupiter' in code else '-',
            'yes' if 'RunWith(MockitoJUnitRunner' in code else '-',
            'yes' if 'org.junit.Test' in code else '-', says))
print()
print(rounds, 'rounds,', with_err, 'with errors,', no_code, 'with no code')
for m, n in errs.most_common(12):
    print(n, m[:140])
