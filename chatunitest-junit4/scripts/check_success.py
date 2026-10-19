"""
read-only. 
compares, for one attempt, the code ChatUniTest recorded in history
(records.json) with the test file it finally saved, and lists the @Test methods in each.
Usage:  python check_success.py <history folder> <saved test .java file> [attemptN]
changes nothing, uses no network.
"""
import sys, glob, os, json, re

hist, saved = sys.argv[1], sys.argv[2]
att = sys.argv[3] if len(sys.argv) > 3 else 'attempt3'
pat = re.compile(r'@Test\b(?:\([^)]*\))?(?:\s|@\w+(?:\([^)]*\))?)*public\s+void\s+(\w+)')

def tests(code):
    return pat.findall(code)

files = sorted(glob.glob(os.path.join(hist, '**', 'records.json'), recursive=True))
found = [f for f in files if os.path.basename(os.path.dirname(f)) == att]
print('records.json files found:', len(files), '| for', att + ':', len(found))
if not found:
    print('attempt folders available:', sorted({os.path.basename(os.path.dirname(f)) for f in files}))
    sys.exit(1)
for f in found:
    for r in json.load(open(f, encoding='utf-8')):
        code = r.get('code') or ''
        print('--- round', r.get('round'), '| hasCode:', r.get('hasCode'), '| hasError:', r.get('hasError'),
              '| @Test methods in recorded code:', tests(code))
        print('    uses @RunWith:', 'RunWith(' in code, '| jupiter:', 'org.junit.jupiter' in code,
              '| org.junit.Test:', 'org.junit.Test' in code)
s = open(saved, encoding='utf-8').read()
print('--- SAVED FILE', os.path.basename(saved))
print('    @Test methods:', tests(s))
print('    uses @RunWith:', '@RunWith(' in s, '| jupiter:', 'org.junit.jupiter' in s)
