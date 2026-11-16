#!/usr/bin/env python3
"""The report's table of the gust system and the approach speed's addition, alone and together: nothing in it is typed by hand.

    python3 fdm/report/mkgust.py          reads results/gust_factorial.json (fdm/gustfactorial.py), writes tab/gust_factorial.tex

One block for each kind of weather, four rows each (neither, the speed alone, the stabilisation alone, both): the flights, the hard landings (a sink over 2 m/s, the structural flag or no
touchdown), the sink's mean and 95th percentile, the flights in which the angle-of-attack protection acted below 500 ft, the distance off the centreline and the nose's heading error at the
first wheel (95th percentiles) and the distance from the aiming point to the end of the rollout.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = (('neither', 'neither'), ('speed', 'speed alone'), ('stab', 'stabilisation alone'), ('both', 'both'), ('fixed', 'fixed +10\\,kt alone'), ('fixedboth', 'fixed +10\\,kt with the system'))


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


if __name__ == '__main__':
    main()
