#!/usr/bin/env python3
"""Reader for the ATTREX flight data of NASA's Global Hawk 872.

The data is the Meteorological Measurement System's (NASA Ames), as ICARTT text files from NASA's ESPO archive,
gzipped. They are read as a stream, never unpacked to disk: a 20 Hz file is 80 to 325 MB of text.

ICARTT (file format index 1001): the first line gives the number of header lines. The header names the
variables, with a scale factor and a missing-value flag for each. The last header line is the column list.

    python3 fdm/attrex.py                 one line per file, then the long steady segments of each
    python3 fdm/attrex.py FILE.ict.gz     the same for one file

In code:
    hdr = header(path)                    names, units, scales, flags, date, platform
    for block in blocks(path, every=20):  dict of numpy arrays in physical units, missing values as NaN
    d = load(path, every=20)              the whole flight as one dict
"""
import glob
import gzip
import itertools
import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'refs', 'tracks', 'ATTREX-2011-2014')

G0, R_AIR, GAMMA = 9.80665, 287.05287, 1.4
FT = 0.3048
KT = 1852.0 / 3600.0

# What "steady" means in the summary, set before looking at the flights. Blocks of BLOCK_S seconds pass when the
# wings stay level, the height changes slowly enough for a cruise-climb but not a climb, and the speed holds.
# Passing blocks in a row make a segment; segments of at least SEG_MIN_S are listed.
BLOCK_S = 60.0
ROLL_MAX_DEG = 2.5
CLIMB_MAX_MS = 1.0
TAS_RANGE_MAX_MS = 5.0
SEG_MIN_S = 600.0
# On the ground or just off it: slower than any flying speed we expect (the stall speed isn't published).
GROUND_TAS_MS = 35.0


def _open(path):
    return gzip.open(path, 'rt', encoding='latin-1') if path.endswith('.gz') else open(path, encoding='latin-1')


def header(path):
    """The ICARTT header as a dict."""
    with _open(path) as f:
        first = f.readline()
        nhead, ffi = (int(x) for x in first.split(',')[:2])
        if ffi != 1001:
            raise ValueError('%s: file format index %d, only 1001 is read' % (path, ffi))
        lines = [first] + [f.readline() for _ in range(nhead - 1)]
    lines = [s.strip() for s in lines]
    date = [int(x) for x in lines[6].split(',')]
    indep = [s.strip() for s in lines[8].split(',')]
    nvar = int(lines[9])
    scales = [float(x) for x in lines[10].split(',')]
    flags = [float(x) for x in lines[11].split(',')]
    names, units, descr = [], [], []
    for s in lines[12:12 + nvar]:
        p = [x.strip() for x in s.split(',', 2)]
        names.append(p[0])
        units.append(p[1] if len(p) > 1 else '')
        descr.append(p[2] if len(p) > 2 else '')
    if len(scales) != nvar or len(flags) != nvar:
        raise ValueError('%s: %d variables, %d scales, %d flags' % (path, nvar, len(scales), len(flags)))
    nspecial = int(lines[12 + nvar])
    special = lines[13 + nvar:13 + nvar + nspecial]
    normal = lines[14 + nvar + nspecial:nhead - 1]
    info = {}
    for s in normal:
        if ':' in s:
            k, v = s.split(':', 1)
            if k.isupper() or k.replace('_', '').isupper():
                info[k.strip()] = v.strip()
    lod = [float(info[k]) for k in ('ULOD_FLAG', 'LLOD_FLAG') if k in info and info[k].lstrip('-').isdigit()]
    return dict(path=path, nhead=nhead, date=tuple(date[:3]), revised=tuple(date[3:6]),
                time=indep[0], names=names, units=units, descr=descr,
                scales=np.array(scales), flags=np.array(flags), lod=lod,
                special=special, platform=info.get('PLATFORM', ''), info=info,
                columns=[s.strip() for s in lines[nhead - 1].split(',')])


def blocks(path, every=1, rows=200000, hdr=None):
    """Yield the data in blocks: a dict of arrays in physical units, the time under 't'.

    every=N keeps each Nth record (20 for one a second out of a 20 Hz file); the others aren't parsed.
    """
    hdr = hdr or header(path)
    with _open(path) as f:
        for _ in range(hdr['nhead']):
            f.readline()
        src = itertools.islice(f, 0, None, every) if every > 1 else f
        while True:
            chunk = list(itertools.islice(src, rows))
            if not chunk:
                return
            a = np.loadtxt(chunk, delimiter=',', ndmin=2)
            out = {'t': a[:, 0]}
            for i, name in enumerate(hdr['names']):
                raw = a[:, i + 1]
                bad = raw == hdr['flags'][i]
                for flag in hdr['lod']:
                    bad |= raw == flag
                out[name] = np.where(bad, np.nan, raw * hdr['scales'][i])
            yield out


def load(path, every=1):
    """The whole file as one dict of arrays, with the header under 'hdr'."""
    hdr = header(path)
    parts = list(blocks(path, every=every, hdr=hdr))
    out = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    out['hdr'] = hdr
    return out


def pressure_altitude(p_hpa):
    """ISA pressure altitude in metres from static pressure in hPa (to 32 km)."""
    p = np.asarray(p_hpa, dtype=float) * 100.0
    p11 = 101325.0 * (1 - 0.0065 * 11000 / 288.15) ** (G0 / (R_AIR * 0.0065))
    p20 = p11 * np.exp(-G0 * 9000 / (R_AIR * 216.65))
    with np.errstate(invalid='ignore', divide='ignore'):
        h_tropo = 288.15 / 0.0065 * (1 - (p / 101325.0) ** (R_AIR * 0.0065 / G0))
        h_strat = 11000 - R_AIR * 216.65 / G0 * np.log(p / p11)
        h_upper = 20000 + 216.65 / 0.001 * ((p / p20) ** (-R_AIR * 0.001 / G0) - 1)
    return np.where(p > p11, h_tropo, np.where(p > p20, h_strat, h_upper))


def isa_temperature(h_m):
    h = np.asarray(h_m, dtype=float)
    return np.where(h < 11000, 288.15 - 0.0065 * h, np.where(h < 20000, 216.65, 216.65 + 0.001 * (h - 20000)))


def derived(d):
    """Add what every file type can give: pressure altitude 'HP' (m), 'M' (Mach) and how each was found."""
    how = {}
    for new, olds in (('LAT', ('G_LAT', 'LN_LAT')), ('LON', ('G_LONG', 'LN_LONG', 'LONG')), ('ALT', ('G_ALT', 'LN_ALT'))):
        for old in olds:
            if old in d and new not in d:
                d[new] = d[old]
    if 'P' in d:
        d['HP'] = pressure_altitude(d['P'])
        how['HP'] = 'from static pressure'
    elif 'P_ALT' in d:
        d['HP'] = d['P_ALT']
        how['HP'] = 'as given'
    if 'MACH' in d:
        d['M'] = d['MACH']
        how['M'] = 'as given'
    elif 'TAS' in d and 'T' in d:
        d['M'] = d['TAS'] / np.sqrt(GAMMA * R_AIR * d['T'])
        how['M'] = 'TAS and measured temperature'
    elif 'TAS' in d and 'HP' in d:
        d['M'] = d['TAS'] / np.sqrt(GAMMA * R_AIR * isa_temperature(d['HP']))
        how['M'] = 'TAS and standard temperature (approximate)'
    d['how'] = how
    return d


def steady_segments(d):
    """Segments of steady flight: list of dicts (start, end in seconds; means), longest first."""
    if 'HP' not in d or 'TAS' not in d:
        return []
    t, h, tas = d['t'], d['HP'], d['TAS']
    roll = d.get('ROLL')
    edges = np.arange(t[0], t[-1] + BLOCK_S, BLOCK_S)
    idx = np.searchsorted(t, edges)
    ok = []
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a < 10 or t[b - 1] - t[a] < 0.8 * BLOCK_S:
            ok.append(False)
            continue
        hh, vv = h[a:b], tas[a:b]
        if np.isnan(hh).mean() > 0.2 or np.isnan(vv).mean() > 0.2 or (roll is not None and np.isnan(roll[a:b]).all()):
            ok.append(False)
            continue
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)   # a block whose ends are all missing: not steady
            climb = abs(np.nanmean(hh[-5:]) - np.nanmean(hh[:5])) / (t[b - 1] - t[a])
        good = climb < CLIMB_MAX_MS and np.nanmax(vv) - np.nanmin(vv) < TAS_RANGE_MAX_MS
        if roll is not None:
            good = good and np.nanmax(np.abs(roll[a:b])) < ROLL_MAX_DEG
        ok.append(bool(good))
    segs, i = [], 0
    while i < len(ok):
        if not ok[i]:
            i += 1
            continue
        j = i
        while j < len(ok) and ok[j]:
            j += 1
        a, b = idx[i], idx[j]
        if t[b - 1] - t[a] >= SEG_MIN_S:
            s = dict(start=t[a], end=t[b - 1], dur=t[b - 1] - t[a], hp=np.nanmean(h[a:b]),
                     dh=np.nanmean(h[b - 5:b]) - np.nanmean(h[a:a + 5]), tas=np.nanmean(tas[a:b]))
            for k in ('M', 'AOA', 'Q', 'PITCH'):
                if k in d:
                    s[k] = np.nanmean(d[k][a:b])
            segs.append(s)
        i = j
    return sorted(segs, key=lambda s: -s['dur'])


def summarise(path, every=None):
    """One file's summary as a dict."""
    hdr = header(path)
    if every is None:
        every = 20 if '20Hz' in os.path.basename(path) else (5 if 'Attitude' in os.path.basename(path) else 1)
    d = derived(load(path, every=every))
    t = d['t']
    s = dict(file=os.path.basename(path), kind=os.path.basename(path).split('_')[0], date='%04d-%02d-%02d' % hdr['date'],
             platform=hdr['platform'], t0=t[0], t1=t[-1], hours=(t[-1] - t[0]) / 3600.0, n=len(t), every=every,
             gaps=float(np.sum(np.diff(t)[np.diff(t) > 60.0])), special=hdr['special'], how=d['how'])
    if 'HP' in d:
        s.update(hp_min=np.nanmin(d['HP']), hp_max=np.nanmax(d['HP']), hp_first=_first(d['HP']), hp_last=_last(d['HP']))
    if 'M' in d:
        s.update(m_max=np.nanmax(d['M']))
        if 'HP' in d:
            high = d['HP'] > 15000
            if high.any():
                s.update(m_cruise=np.nanmedian(d['M'][high]), tas_cruise=np.nanmedian(d['TAS'][high]),
                         hours_high=float(high.sum()) * np.median(np.diff(t)) / 3600.0)
    if 'TAS' in d:
        s.update(tas_first=_first(d['TAS']), tas_last=_last(d['TAS']))
        s['takeoff'] = _end_state(s['tas_first'], s.get('hp_first'), s.get('hp_min'))
        s['landing'] = _end_state(s['tas_last'], s.get('hp_last'), s.get('hp_min'))
    if 'AOA' in d:
        s.update(aoa_min=np.nanpercentile(d['AOA'], 1), aoa_max=np.nanpercentile(d['AOA'], 99))
    s['segments'] = steady_segments(d)
    return s


def _first(x):
    x = x[~np.isnan(x)]
    return float(x[0]) if len(x) else float('nan')


def _last(x):
    x = x[~np.isnan(x)]
    return float(x[-1]) if len(x) else float('nan')


def _end_state(tas, hp, hp_min):
    """Where the record starts or ends: on the ground, low (within 300 m of its lowest point), or in flight."""
    if tas < GROUND_TAS_MS:
        return 'ground'
    if hp is not None and hp - hp_min < 300.0:
        return 'low'
    return 'in flight'


def hms(sec):
    sec = int(round(sec))
    return '%02d:%02d:%02d' % (sec // 3600 % 24, sec // 60 % 60, sec % 60)


def files():
    out = []
    for kind in ('MMS-20Hz', 'MMS-1HZ', 'MMS-FlightPath', 'MMS-MetData', 'MMS-Attitude'):
        out += sorted(glob.glob(os.path.join(DATA, kind, '*.ict*')))
    return out


def best_per_flight(paths):
    """One file per flight date: the 20 Hz file if there is one, else the 1 Hz, else the flight path.

    The names of the position columns changed between campaigns (LN_LAT in 2013, G_LAT from December 2013);
    derived() gives both as LAT, LON and ALT.
    """
    seen = {}
    for p in paths:
        date = os.path.basename(p).split('_')[2]
        seen.setdefault(date, p)
    return [seen[k] for k in sorted(seen)]


def report(paths, out=sys.stdout):
    w = out.write
    w('ATTREX, NASA Global Hawk 872: one row per flight, from the best file of each date\n')
    w('steady: blocks of %.0f s with roll under %.1f deg, height change under %.1f m/s, TAS range under %.0f m/s; '
      'segments of %.0f min or more\n\n' % (BLOCK_S, ROLL_MAX_DEG, CLIMB_MAX_MS, TAS_RANGE_MAX_MS, SEG_MIN_S / 60))
    w('%-10s %-9s %8s %5s  %-9s %-9s %7s %7s %6s %6s %6s %5s %6s\n' % (
        'date', 'file', 'start', 'hours', 'begins', 'ends', 'max ft', 'h>49k', 'M crz', 'KTAS', 'M max', 'segs', 'seg h'))
    all_s = []
    for p in paths:
        s = summarise(p)
        all_s.append(s)
        seg_h = sum(x['dur'] for x in s['segments']) / 3600.0
        w('%-10s %-9s %8s %5.1f  %-9s %-9s %7.0f %7.1f %6.3f %6.0f %6.3f %5d %6.1f\n' % (
            s['date'], s['kind'].replace('MMS-', ''), hms(s['t0']), s['hours'], s.get('takeoff', '-'),
            s.get('landing', '-'), s.get('hp_max', np.nan) / FT, s.get('hours_high', 0.0), s.get('m_cruise', np.nan),
            s.get('tas_cruise', np.nan) / KT, s.get('m_max', np.nan), len(s['segments']), seg_h))
        out.flush()
    w('\nbegins/ends: ground = TAS under %.0f m/s; low = within 300 m of the record\'s lowest point; else in flight\n'
      % GROUND_TAS_MS)
    w('h>49k: hours above 15,000 m pressure altitude; M crz and KTAS: medians there\n')
    for s in all_s:
        w('\n%s  %s  %s\n' % (s['date'], s['file'], s['platform']))
        w('  first sample: %.0f ft, %.0f KTAS; last: %.0f ft, %.0f KTAS; gaps over a minute: %.0f s in all\n' % (
            s.get('hp_first', np.nan) / FT, s.get('tas_first', np.nan) / KT, s.get('hp_last', np.nan) / FT,
            s.get('tas_last', np.nan) / KT, s['gaps']))
        for line in s['special']:
            w('  note in file: %s\n' % line)
        if 'aoa_min' in s:
            w('  angle of attack at the probe, 1st to 99th percentile: %.1f to %.1f deg\n' % (s['aoa_min'], s['aoa_max']))
        for x in s['segments'][:6]:
            w('  steady %s-%s %5.0f min  %6.0f ft (%+5.0f ft)  M %.3f  %3.0f KTAS%s\n' % (
                hms(x['start']), hms(x['end']), x['dur'] / 60, x['hp'] / FT, x['dh'] / FT, x.get('M', np.nan),
                x['tas'] / KT, '  AoA %.2f deg  q %.1f hPa' % (x['AOA'], x['Q']) if 'AOA' in x else ''))
    return all_s


if __name__ == '__main__':
    args = sys.argv[1:]
    report(args if args else best_per_flight(files()))
