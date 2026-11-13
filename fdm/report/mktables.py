#!/usr/bin/env python3
"""The report's tables, from the check logs: nothing in them is typed by hand.

    python3 fdm/report/mktables.py          reads fdm/report/results/*.txt (fdm/check_all.sh), writes fdm/report/tab/

Each check is grouped by what it is held to (labels.py). Every MISS needs its cause in causes.json (log, tag and a
few words of the check's name), or the run stops: a miss cannot get into the report unexplained, and a cause for a
miss that is gone is reported as stale. A log whose own count differs from its lines stops the run too.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
TAB = os.path.join(HERE, 'tab')

# log, the report's heading, and labels: the default for the log, then (tag pattern, label) exceptions, first match wins
STATUS = re.compile(r'\s(pass|MISS|reported)(?=\s|$)')
TAG = re.compile(r'^[A-Z]{1,2}\d+[a-z]?$')
FITTED = re.compile(r'after the fit|after setting|fitted to')


def read(name):
    """[(tag, check, status, detail)] and the log's own count line."""
    rows, count = [], None
    for line in open(os.path.join(RESULTS, name + '.txt'), encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        m = re.search(r'(\d+) checks, (\d+) pass(?:, (\d+) miss)?', line)
        if m:
            count = (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
            continue
        m = STATUS.search(line)
        if not m or line.lstrip().startswith(('check ', 'not checks')):
            continue
        head, detail = line[:m.start()].strip(), line[m.end():].strip()
        first = head.split(None, 1)
        tag = first[0] if first and TAG.match(first[0]) else ''
        check = re.sub(r'\s{2,}', '  ', first[1] if tag and len(first) > 1 else head)
        rows.append((tag, check, m.group(1), detail))
    return rows, count


def tex(s):
    s = s.replace('\\', r'\textbackslash{}')
    for a, b in (('&', r'\&'), ('%', r'\%'), ('_', r'\_'), ('#', r'\#'), ('$', r'\$'), ('{', r'\{'), ('}', r'\}'), ('~', r'\textasciitilde{}'),
                 ('^', r'\textasciicircum{}'), ('"', "''"), ('<', r'\textless{}'), ('>', r'\textgreater{}'), ('°', r'\textdegree{}')):
        if a in ('{', '}') and b in s:
            continue
        s = s.replace(a, b)
    return s.replace(r'\textbackslash\{\}', r'\textbackslash{}')


def group_of(labels, tag, check):
    for pattern, group in labels[1:]:
        if re.search(pattern, tag + ' ' + check):
            return group
    return labels[0]


def main(logs, groups):
    os.makedirs(TAB, exist_ok=True)
    causes = json.load(open(os.path.join(HERE, 'causes.json')))
    used, problems = set(), []
    table = []                                  # (title, {group: [pass, miss]}, reported)
    numbers, misses = [], []
    for name, title, labels in logs:
        if not os.path.exists(os.path.join(RESULTS, name + '.txt')):
            problems.append('%s: no log' % name)
            continue
        rows, count = read(name)
        checks = [r for r in rows if r[2] != 'reported']
        passed = sum(r[2] == 'pass' for r in checks)
        missed = len(checks) - passed
        if count is not None and (count[1], count[2]) != (passed, missed):
            problems.append('%s: the log counts %s, its lines give %d pass, %d miss' % (name, count, passed, missed))
        by = {}
        body = []
        for tag, check, status, detail in rows:
            group = group_of(labels, tag, check)
            if group not in groups:
                problems.append('%s %s %s: no group' % (name, tag, check[:50]))
                continue
            # a check made after a fit to the same figure is marked: it shows the fit worked, not that the model is right
            fitted = bool(FITTED.search(detail))
            if status != 'reported':
                by.setdefault(group, [0, 0, 0])[status == 'MISS'] += 1
                by[group][2] += fitted and status == 'pass'
            body.append('%s & %s & %s & %s & %s \\\\' % (tex(tag), tex(check), (group + ('*' if fitted else '')) if status != 'reported' else '', {'MISS': r'\textbf{MISS}', 'pass': 'pass', 'reported': 'rep.'}[status], tex(detail)))
            if status == 'MISS':
                found = [c for c in causes if c['log'] == name and c['tag'] == tag and c['words'] in check]
                if not found:
                    problems.append('%s %s %s: a MISS with no cause in causes.json' % (name, tag, check[:60]))
                else:
                    used.add(id(found[0]))
                    misses.append((found[0]['kind'], '%s & %s & %s \\\\' % (tex((tag + ' ' + check).strip()), tex(title), tex(found[0]['cause']))))
        table.append((title, by, len(rows) - len(checks)))
        with open(os.path.join(TAB, 'checks_%s.tex' % name.replace('_checks', '')), 'w') as fh:
            fh.write('\n'.join(body) + '\n')
    for c in causes:
        if id(c) not in used:
            problems.append('causes.json: stale, no such miss now: %s %s %s' % (c['log'], c['tag'], c['words']))
    with open(os.path.join(TAB, 'misses.tex'), 'w') as fh:
        fh.write('\n'.join(m[1] for m in misses) + '\n\\bottomrule\n')              # the rule here: TeX takes none after an \\input in a table
    # the summary: a row a log, a column a group, "pass/miss"
    order = [g for g in groups if any(g in by for _, by, _ in table)]
    cell = lambda v: '' if v is None else ('%d' % v[0] if not v[1] else '%d/\\textbf{%d}' % (v[0], v[1]))
    total = {g: [sum(by.get(g, [0, 0, 0])[k] for _, by, _ in table) for k in (0, 1, 2)] for g in order}
    with open(os.path.join(TAB, 'tab_checks.tex'), 'w') as fh:
        fh.write('\\begin{tabularx}{\\columnwidth}{@{}>{\\raggedright\\arraybackslash}X%s@{}}\n\\toprule\n & %s \\\\\n\\midrule\n' % ('r' * len(order), ' & '.join(order)))
        for title, by, _ in table:
            fh.write('%s & %s \\\\\n' % (tex(title), ' & '.join(cell(by.get(g)) for g in order)))
        fh.write('\\midrule\nAll & %s \\\\\n\\bottomrule\n\\end{tabularx}\n' % ' & '.join(cell(total[g]) for g in order))
    passed, missed = sum(v[0] for v in total.values()), sum(v[1] for v in total.values())
    fitted = sum(v[2] for v in total.values())
    tests = len(re.findall(r'(?m)\b(?:OK|ok)\s*$', open(os.path.join(RESULTS, 'gcs_tests.txt')).read()))
    stamp = open(os.path.join(RESULTS, 'commit.txt')).read().split('\n')
    # figures the text quotes from FlightGear runs: read from the logs, so a rerun cannot leave them stale
    def grab(log, pattern, names):
        m = re.search(pattern, open(os.path.join(RESULTS, log + '.txt'), errors='replace').read())
        if not m:
            problems.append('%s: the text quotes a figure the log no longer has (%s)' % (log, pattern[:50]))
            return ''
        return ''.join('\\newcommand{\\%s}{%s}\n' % (n, v) for n, v in zip(names, m.groups()))
    quoted = (grab('phase9b_checks', r'at (\d+) lb; under 15 kt (\d+) ft past the aiming point \(the flight model alone at that weight: (\d+) ft', ('FgLandWeight', 'FgLandPast', 'FgLandModel'))
              + grab('phase9d_checks', r'the camera within ([\d.]+) deg of the point', ('FgCamPoint',))
              + grab('phase9d_checks', r'the camera within ([\d.]+) deg of it', ('FgCamShip',))
              + grab('phase9a_checks', r'height (\d+) to (\d+) ft, ([\d.]+) to ([\d.]+) KCAS, bank within ([\d.]+) deg', ('FgAirHLo', 'FgAirHHi', 'FgAirVLo', 'FgAirVHi', 'FgAirBank'))
              + grab('phase9c_checks', r'([\d.]+) deg apart \(12.8 px a deg\)', ('FgHudHorizon',)))
    kinds = {}
    for kind, _ in misses:
        kinds[kind] = kinds.get(kind, 0) + 1
    with open(os.path.join(TAB, 'numbers.tex'), 'w') as fh:
        fh.write('\\newcommand{\\Npass}{%d}\\newcommand{\\Nmiss}{%d}\\newcommand{\\Nchecks}{%d}\\newcommand{\\Nreported}{%d}\\newcommand{\\Nstationtests}{%d}\\newcommand{\\Nfitted}{%d}\n' % (
            passed, missed, passed + missed, sum(t[2] for t in table), tests, fitted))
        fh.write(''.join('\\newcommand{\\N%spass}{%d}\\newcommand{\\N%smiss}{%d}\n' % (g, total[g][0], g, total[g][1]) for g in order))
        fh.write(''.join('\\newcommand{\\Nkind%s}{%d}\n' % (k, v) for k, v in sorted(kinds.items())))
        fh.write(quoted)
        fh.write('\\newcommand{\\Ncommit}{%s}\\newcommand{\\Ndate}{%s}\n' % (stamp[0], stamp[1] if len(stamp) > 1 else ''))
    print('%d checks: %d pass (%d of them after a fit), %d miss; %d reported; %d station test files; by group %s; misses by kind %s' % (
        passed + missed, passed, fitted, missed, sum(t[2] for t in table), tests, {g: tuple(total[g]) for g in order}, kinds))
    for p in problems:
        print('PROBLEM', p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    from labels import GROUPS, LOGS
    sys.exit(main(LOGS, GROUPS))
