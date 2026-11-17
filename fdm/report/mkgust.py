#!/usr/bin/env python3
"""The report's table of the gust system and the approach speed's addition, alone and together: nothing in it is typed by hand.

    python3 fdm/report/mkgust.py          reads results/gust_factorial.json (fdm/gustfactorial.py), writes tab/gust_factorial.tex

One block for each kind of weather, four rows each (neither, the speed alone, the stabilisation alone, both): the flights, the hard landings (a sink over 2 m/s, the structural flag or no
touchdown), the sink's mean and 95th percentile, the flights in which the angle-of-attack protection acted below 500 ft, the distance off the centreline and the nose's heading error at the
first wheel (95th percentiles) and the distance from the aiming point to the end of the rollout.
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = (('neither', 'neither'), ('speed', 'speed alone'), ('stab', 'stabilisation alone'), ('both', 'both'), ('fixed', 'fixed +10\\,kt alone'), ('fixedboth', 'fixed +10\\,kt with the system'))


def mi(s):
    """a typeset minus sign"""
    return s.replace('-', '$-$')


def tex(s):
    return s.replace('&', r'\&').replace('%', r'\%').replace('_', r'\_').replace('#', r'\#')


SHOWN = ('stab-neither', 'speed-neither', 'both-neither', 'fixed-neither', 'fixedboth-stab')        # the contrasts the report prints (the others are in the JSON)
LABEL = {'speed': 'speed', 'stab': 'stabilisation', 'both': 'both', 'neither': 'neither', 'fixed': 'fixed +10\\,kt', 'fixedboth': 'fixed +10\\,kt with the system'}


def pfmt(p):
    return '$<$0.001' if p < 0.001 else '%.3f' % p


def ci(t, fmt):
    return (fmt + r' [' + fmt + r', ' + fmt + r']') % (t[0], t[1], t[2])


def contrasts_table(data):
    """the paired contrasts: the hard landings (each arm's count, the pairs that differ each way, the exact McNemar p) and the mean paired differences with 95 % bootstrap intervals"""
    lines = [r'\begin{tabular}{@{}l l r r r r l l l@{}}', r'\toprule',
             r'Contrast & Hard & Only first & Only second & $p$ & & $\Delta$ sink (m/s) & $\Delta$ line (ft) & $\Delta$ landing (ft) \\']
    for entry in data:
        cs = entry.get('contrasts') or {}
        if not cs:
            continue
        lines.append(r'\midrule')
        lines.append(r'\multicolumn{9}{@{}l}{\textbf{%s}} \\' % tex(entry['weather']))
        for key, c in cs.items():
            if key not in SHOWN:
                continue
            a, b = key.split('-')
            lines.append('\\quad %s against %s & %d against %d & %d & %d & %s & & %s & %s & %s \\\\' % (LABEL[a], LABEL[b], c['hard_a'], c['hard_b'], c['only_a'], c['only_b'], pfmt(c['p_hard']),
                                                                                              ci(c['d_sink'], '%+.2f'), ci(c['d_line'], '%+.1f'), ci(c['d_total'], '%+.0f')))
    lines += [r'\bottomrule', r'\end{tabular}']
    out = os.path.join(HERE, 'tab', 'gust_contrasts.tex')
    open(out, 'w').write('\n'.join(lines) + '\n')
    print('wrote', out)


def main():
    path = os.path.join(HERE, 'results', 'gust_factorial.json')
    data = json.load(open(path))
    lines = [r'\begin{tabular}{@{}l r r r r r r r r@{}}', r'\toprule',
             r'Arm & Flights & Hard & Sink, mean (m/s) & Sink, 95\,\% & Events & Line, 95\,\% (ft) & Nose, 95\,\% ($^\circ$) & Landing (ft) \\']
    for entry in data:
        lines.append(r'\midrule')
        lines.append(r'\multicolumn{9}{@{}l}{\textbf{%s}} \\' % tex(entry['weather']))
        for key, label in ARMS:
            m = entry['arms'].get(key)
            if not m:
                continue
            lines.append('\\quad %s & %d & %d & %.2f & %.2f & %d & %.1f & %.1f & %s \\\\' % (label, m['n'], m['hard'], m['sink_mean'], m['sink95'], m['events'], m['line95'], m['nose95'],
                                                                                    '{:,.0f}'.format(m['total']).replace(',', r'\,')))
    lines += [r'\bottomrule', r'\end{tabular}']
    out = os.path.join(HERE, 'tab', 'gust_factorial.tex')
    open(out, 'w').write('\n'.join(lines) + '\n')
    print('wrote', out, '(%d weathers)' % len(data))
    contrasts_table(data)


RULE_ARMS = (('neither', 'no addition'), ('stab', 'stabilisation alone'), ('both', 'own pick and stabilisation'), ('boeing', 'Boeing rule'), ('boeingstab', 'Boeing rule with the stabilisation'),
             ('airbus', 'Airbus rule'), ('airbusstab', 'Airbus rule with the stabilisation'))
RULE_CONTRASTS = {'pooled': ('both-neither', 'boeing-neither', 'airbus-neither', 'both-boeing', 'both-airbus', 'both-boeingstab', 'both-airbusstab'), 'abeam': ('boeing-neither', 'airbus-neither', 'both-boeing', 'both-airbus'),
                  'shear': ('stab-neither', 'boeing-neither', 'airbus-neither', 'both-boeing', 'both-airbus')}
RLABEL = dict(LABEL, boeing='Boeing rule', airbus='Airbus rule', boeingstab='Boeing rule with the stabilisation', airbusstab='Airbus rule with the stabilisation', stab='stabilisation',
              both='own pick and stabilisation', neither='no addition')


def rules_tables():
    """the airliners' rules against the aircraft's own laws (results/gust_factorial_v2_rules.json, _crazy.json: fdm/gustv2.py, fdm/gustfactorial.py): the arms and the contrasts"""
    R = os.path.join(HERE, 'results')
    pooled = json.load(open(os.path.join(R, 'gust_factorial_v2_rules.json')))[0]
    crazy = json.load(open(os.path.join(R, 'gust_factorial_v2_crazy.json')))
    blocks = [('pooled', 'seven turbulence weathers pooled, 20\\,800\\,lb (%d sequences)' % pooled['arms']['neither']['n'], pooled),
              ('abeam', '28\\,kt abeam with turbulence, 26\\,750\\,lb (%d sequences)' % crazy[0]['arms']['neither']['n'], crazy[0]),
              ('shear', '36\\,kt abeam with the shear to 85\\,kt at 500\\,ft, 26\\,750\\,lb (%d sequences)' % crazy[1]['arms']['neither']['n'], crazy[1])]
    lines = [r'\begin{tabular}{@{}l r r r r r r@{}}', r'\toprule', r'Arm & Hard (flagged) & Events & Sink, mean (m/s) & Sink, 95\,\% & Line, 95\,\% (ft) & Landing (ft) \\']
    for key, title, e in blocks:
        lines += [r'\midrule', r'\multicolumn{7}{@{}l}{\textbf{%s}} \\' % title]
        for a, label in RULE_ARMS:
            m = e['arms'][a]
            lines.append('\\quad %s & %d (%d) & %d & %.2f & %.2f & %.1f & %s \\\\' % (label, m['hard'], m['flag'], m['events'], m['sink_mean'], m['sink95'], m['line95'], '{:,.0f}'.format(m['total']).replace(',', r'\,')))
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(HERE, 'tab', 'gust_rules.tex'), 'w').write('\n'.join(lines) + '\n')
    lines = [r'\begin{tabular}{@{}l l r r r l l@{}}', r'\toprule', r'Contrast & Hard & Only first & Only second & $p$ & $\Delta$ sink (m/s) & $\Delta$ landing (ft) \\']
    for key, title, e in blocks:
        lines += [r'\midrule', r'\multicolumn{7}{@{}l}{\textbf{%s}} \\' % title]
        for ck in RULE_CONTRASTS[key]:
            c = e['contrasts'][ck]
            a, b = ck.split('-')
            lines.append('\\quad %s against %s & %d against %d & %d & %d & %s & %s & %s \\\\' % (RLABEL[a], RLABEL[b], c['hard_a'], c['hard_b'], c['only_a'], c['only_b'], pfmt(c['p_hard']),
                                                                                              ci(c['d_sink'], '%+.2f'), ci(c['d_total'], '%+.0f')))
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(HERE, 'tab', 'gust_rules_contrasts.tex'), 'w').write('\n'.join(lines) + '\n')
    print('wrote tab/gust_rules.tex and tab/gust_rules_contrasts.tex')


def lat_table():
    """the old landing law against the present one, on the three sets, the wing tips with and without the wing's bending (results/lat_roll_loop.json: mkstudy.py)"""
    p = os.path.join(HERE, 'results', 'lat_roll_loop.json')
    if not os.path.exists(p):
        return
    D = json.load(open(p))
    lines = [r'\begin{tabular}{@{}l l r r r r r r r r r@{}}', r'\toprule',
             r'Set & Law & Flights & \multicolumn{2}{c}{Tip at the ground, rigid / bent} & Lowest tip, bent (ft) & Bank at first wheel (mean, max) & Line (mean, 95\,\%) (ft) & Beyond 30\,ft & Hard \\']
    for s, e in D.items():
        lines.append(r'\midrule')
        for k, (lk, name) in enumerate((('law2', 'old'), ('law3', 'present'))):
            m = e[lk]
            lines.append('%s & %s & %d & %d & %d & %s & %.1f, %.1f$^\\circ$ & %.1f, %.1f & %d & %d \\\\' % (('%s (%s)' % (s, e['label'])) if k == 0 else '', name, m['n'], m['rigid_le0'], m['flex_le0'], mi('%+.2f' % m['flex_min']),
                                                                                          m['bank_td_mean'], m['bank_td_max'], m['line_mean'], m['line_p95'], m['line_over30'], m['hard']))
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(HERE, 'tab', 'lat_roll_loop.tex'), 'w').write('\n'.join(lines) + '\n')
    print('wrote tab/lat_roll_loop.tex')


def drift_table():
    """the flare's drift by weight and crosswind, and the touchdown error with the aim offset (results/flare_drift.json: mkstudy.py)"""
    p = os.path.join(HERE, 'results', 'flare_drift.json')
    if not os.path.exists(p):
        return
    D = json.load(open(p))
    rows = D['rows']
    wts = (12450, 19100, 26750)
    winds = sorted(set(int(r['name'].split('_x')[1]) for r in rows))
    get = lambda aim, wt, wd: next((r for r in rows if r['aim'] == aim and round(r['weight']) == wt and int(r['name'].split('_x')[1]) == wd), None)
    head = ' & '.join('%s\\,lb' % '{:,}'.format(w).replace(',', r'\,') for w in wts)
    lines = [r'\begin{tabular}{@{}l r r r@{}}', r'\toprule', r'Crosswind at the wheels & ' + head + r' \\', r'\midrule',
             r'\multicolumn{4}{@{}l}{\textbf{drift from 15\,ft to the first wheel, downwind (ft)}} \\']
    for wd in winds:
        xs = [get(False, wt, wd) for wt in wts]
        kt = np.mean([r['xw'] for r in xs if r])
        lines.append('\\quad %.0f\\,kt & %s \\\\' % (kt, ' & '.join('%.1f' % r['drift15'] if r else '--' for r in xs)))
    lines += [r'\midrule', r'\multicolumn{4}{@{}l}{\textbf{touchdown error with the offset, upwind positive (ft)}} \\']
    for wd in winds:
        xa = [get(True, wt, wd) for wt in wts]
        if not any(xa):
            continue
        kt = np.mean([r['xw'] for r in xa if r])
        lines.append('\\quad %.0f\\,kt & %s \\\\' % (kt, ' & '.join((mi('%+.1f' % r['x_td']) if abs(r['x_td']) >= 0.05 else '0.0') if r else '--' for r in xa)))
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(HERE, 'tab', 'flare_drift.tex'), 'w').write('\n'.join(lines) + '\n')
    print('wrote tab/flare_drift.tex')


V3_ARMS = (('neither', 'no addition'), ('both', 'own pick and stabilisation'), ('boeing', 'Boeing rule'), ('boeingstab', 'Boeing rule with the stabilisation'), ('airbus', 'Airbus rule'),
           ('airbusstab', 'Airbus rule with the stabilisation'))
V3_CONTRASTS = ('both-neither', 'boeing-neither', 'airbus-neither', 'both-boeing', 'both-airbus', 'both-boeingstab', 'both-airbusstab')


def rules_v3_tables():
    """the airliners' rules flown again on the present laws at two weights (results/gust_factorial_v3.json: fdm/gustv3.py summary): the arms and the contrasts"""
    p = os.path.join(HERE, 'results', 'gust_factorial_v3.json')
    if not os.path.exists(p):
        return
    D = json.load(open(p))
    lines = [r'\begin{tabular}{@{}l r r r r r r r@{}}', r'\toprule', r'Arm & Hard (flagged) & Events & Room, median ($^\circ$) & Sink, mean (m/s) & Sink, 95\,\% & Line, 95\,\% (ft) & Landing (ft) \\']
    for e in D:
        lines += [r'\midrule', r'\multicolumn{8}{@{}l}{\textbf{%s}} \\' % tex(e['weather'].replace('pooled, both weights', 'pooled, both weights').replace(' lb', '\\,lb'))]
        for a, label in V3_ARMS:
            m = e['arms'][a]
            lines.append('\\quad %s & %d (%d) & %d & %s & %.2f & %.2f & %.1f & %s \\\\' % (label, m['hard'], m['flag'], m['events'], mi('%+.1f' % e['margin_median'][a]), m['sink_mean'], m['sink95'], m['line95'],
                                                                                 '{:,.0f}'.format(m['total']).replace(',', r'\,')))
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(HERE, 'tab', 'gust_rules_v3.tex'), 'w').write('\n'.join(lines) + '\n')
    lines = [r'\begin{tabular}{@{}l l r r r l l@{}}', r'\toprule', r'Contrast & Hard & Only first & Only second & $p$ & $\Delta$ sink (m/s) & $\Delta$ landing (ft) \\']
    for e in D:
        lines += [r'\midrule', r'\multicolumn{7}{@{}l}{\textbf{%s}} \\' % tex(e['weather'].replace(' lb', '\\,lb'))]
        for ck in V3_CONTRASTS:
            c = e['contrasts'][ck]
            a, b = ck.split('-')
            lines.append('\\quad %s against %s & %d against %d & %d & %d & %s & %s & %s \\\\' % (RLABEL[a], RLABEL[b], c['hard_a'], c['hard_b'], c['only_a'], c['only_b'], pfmt(c['p_hard']),
                                                                                              ci(c['d_sink'], '%+.2f'), ci(c['d_total'], '%+.0f')))
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(HERE, 'tab', 'gust_rules_v3_contrasts.tex'), 'w').write('\n'.join(lines) + '\n')
    print('wrote tab/gust_rules_v3.tex and tab/gust_rules_v3_contrasts.tex')


if __name__ == '__main__':
    main()
    rules_tables()
    rules_v3_tables()
    lat_table()
    drift_table()
