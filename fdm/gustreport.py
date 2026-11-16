#!/usr/bin/env python3
"""Reads the records fdm/gustbench.py wrote and lays a single-gust sweep out as a grid (docs/PLAN.md, "Gusts: find out first").

    python3 fdm/gustreport.py [--metric sink|xt|nose|speed|rollout|bank|nz|alpha] FILE.jsonl [FILE2.jsonl]

One grid a (weight, rise, hold) group: a row for each gust size, a column for each height it began at. A cell is the metric at the touchdown (default: the sink in m/s) and, after it, what the landing's
contracts would break: G the gate (final.gate), T the touchdown (flare.touchdown), R the rollout line, C the control margin, N never down, S the structural flag. With two files the second's cell follows the first's,
after a slash (the system off, the system on).
"""
import json
import re
import sys

RX = re.compile(r'w=(\d+).*?g=(\w):(-?[\d.]+)@(\d+):([\d.]+):([\d.]+)')
CODE = {'final.gate': 'G', 'flare.touchdown': 'T', 'rollout.line': 'R', 'control.margin': 'C', 'never down': 'N'}


def cell(r, metric):
    if r is None:
        return '.'
    flags = ''.join(CODE.get(b, '?') for b in r['broke']) + ('S' if r.get('overstress', 0) else '')
    if r.get('mgr'):
        td = r['touchdown']
        return ('%d' % len(r['missed'])) + ('A' if r['abandoned'] else '') + ('' if td else 'N')
    if not r['down']:
        return 'N'
    b = r['below500']
    v = dict(sink=r['sink_ms'], xt=r['xt_td_ft'], nose=r['nose_off_deg'], speed=r['speed_err_td'], rollout=r['rollout_xt_ft'], bank=r['bank_td'],
             nz=b['nz'][1], alpha=b['alpha_margin'])[metric]
    return ('%.1f' % v) + flags


def load(path):
    out = {}
    for line in open(path):
        r = json.loads(line)
        m = RX.search(r['name'])
        if m:
            w, axis, kt, h, rise, hold = m.groups()
            out[(int(w), axis, float(kt), int(h), float(rise), float(hold))] = r
    return out


def loadall(path):
    out = {}
    for line in open(path):
        r = json.loads(line)
        out[r['name']] = r
    return out


def summary(off, on):
    """two files of the same cases (the system off, on): the landings that were hard (the sink over 2 m/s, or never down, or the structural flag), and the cases the system made worse"""
    names = [n for n in off if n in on]
    def hard(r):
        return (not r['down']) or r['sink_ms'] > 2.0 or r.get('overstress', 0) > 0
    def sink(r):
        return r['sink_ms'] if r['down'] else 99.0
    ho, hn = sum(hard(off[n]) for n in names), sum(hard(on[n]) for n in names)
    better = [n for n in names if sink(on[n]) < sink(off[n]) - 0.5]
    worse = [n for n in names if sink(on[n]) > sink(off[n]) + 0.5]
    print('%d cases: hard landings (sink over 2 m/s, structural flag, or never down) %d off, %d on; better by over 0.5 m/s: %d, worse by over 0.5 m/s: %d' % (len(names), ho, hn, len(better), len(worse)))
    for n in worse[:30]:
        print('   worse: %-50s off %.2f on %.2f' % (n, sink(off[n]), sink(on[n])))


def main():
    args = sys.argv[1:]
    metric = 'sink'
    if args and args[0] == '--metric':
        metric, args = args[1], args[2:]
    if args and args[0] == '--summary':
        summary(loadall(args[1]), loadall(args[2]))
        return
    data = [load(p) for p in args]
    keys = set().union(*[set(d) for d in data])
    groups = sorted({(k[0], k[1], k[4], k[5]) for k in keys})
    for w, axis, rise, hold in groups:
        ks = [k for k in keys if (k[0], k[1], k[4], k[5]) == (w, axis, rise, hold)]
        heights = sorted({k[3] for k in ks}, reverse=True)
        sizes = sorted({k[2] for k in ks})
        print('\n%d lb, %s gust, rise %g s, hold %g s: %s at the touchdown; rows the gust (kt), columns the height it begins at (ft)' % (w, {'a': 'along (+ headwind)', 'x': 'across (+ from the right)', 'v': 'vertical (+ up)'}[axis], rise, hold, metric))
        wd = 6 * len(data) + 3
        print('%7s ' % '' + ' '.join('%*d' % (wd, h) for h in heights))
        for kt in sizes:
            row = []
            for h in heights:
                k = (w, axis, kt, h, rise, hold)
                row.append('%*s' % (wd, '/'.join(cell(d.get(k), metric) for d in data)))
            print('%+7.0f ' % kt + ' '.join(row))


if __name__ == '__main__':
    main()
