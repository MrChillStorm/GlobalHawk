"""An airport's ground network and runway ends, as the aircraft sends them to the station (the `airport` command, docs/GCS.md).

The data are FlightGear's own, from the scenery folder: Airports/E/F/H/EFHK.groundnet.xml (parking spots, taxi nodes and the arcs between them, every arc named
for its taxiway or, on a runway, for the runway) and EFHK.threshold.xml (the runway ends). In FlightGear the aircraft's Nasal reads them (GlobalHawk/Nasal/onboard.nas); this is
the same in Python for the headless checks and the demo server, and GlobalHawk/gcs/tests/fixtures holds a made-up field both are checked on.

The message (compact; positions in the lists are the indices the arcs use, not the file's):
    {"icao": "EFHK",
     "parking": [{"n": "121", "t": "tie_down", "lat": 60.32097, "lon": 24.96737, "h": 138.0, "r": 26.0}, ...],      r: radius, m
     "nodes": [[lat, lon], ...],
     "arcs": [[a, b, k], ...],                                           a, b: indices into nodes; k: index into names; each arc once (the file lists both ways)
     "names": ["04R/22L", "AK", ...],
     "runways": [{"n": "22L", "lat": 60.330658, "lon": 24.979042, "h": 227.51, "displ": 0.0, "stopw": 68.0}, ...]}      displ, stopw: m
"""
import json
import os
import re
import xml.etree.ElementTree as ET

MAX_BYTES = 100000                      # what the station is willing to take over the link (docs/PLAN.md, "Starting at a stand from the planner")


def _dm(s):
    """'N60 18.59300820' / 'E24 57.33997380' to degrees"""
    m = re.match(r'([NSEW])\s*(\d+)\s+([\d.]+)', s.strip())
    if not m:
        return float(s)
    v = int(m.group(2)) + float(m.group(3)) / 60.0
    return -v if m.group(1) in 'SW' else v


def scenery_dirs():
    """Where the scenery may be: FG_SCENERY (FlightGear's own variable) and the usual places for TerraSync on this machine. FlightGear itself knows; this is for the checks and the demo server."""
    out = [d for d in os.environ.get('FG_SCENERY', '').split(os.pathsep) if d]
    home = os.path.expanduser('~')
    for d in ('Library/Application Support/FlightGear/TerraSync_WS3', 'Library/Application Support/FlightGear/TerraSync', '.fgfs/TerraSync', '.fgfs/TerraSync_WS3',
              'AppData/Roaming/flightgear.org/TerraSync', 'AppData/Roaming/flightgear.org/TerraSync_WS3'):
        out.append(os.path.join(home, d))
    return out


def valid(icao):
    return isinstance(icao, str) and re.fullmatch(r'[A-Z0-9]{4}', icao) is not None


def load(icao, dirs=None):
    """The airport message for an ICAO code, or ValueError(why not)."""
    icao = (icao or '').strip().upper() if isinstance(icao, str) else icao
    if not valid(icao):
        raise ValueError('an airport is four letters or digits, like EFHK')
    path = None
    for d in dirs or scenery_dirs():
        p = os.path.join(d, 'Airports', icao[0], icao[1], icao[2], icao + '.groundnet.xml')
        if os.path.exists(p):
            path = p
            break
    if path is None:
        raise ValueError('no ground network for %s in the scenery' % icao)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ValueError('the ground network of %s cannot be read (%s)' % (icao, e))
    parking = []
    for p in root.iter('Parking'):
        parking.append(dict(n=p.get('name') or '', t=p.get('type') or '', lat=round(_dm(p.get('lat')), 6), lon=round(_dm(p.get('lon')), 6),
                            h=round(float(p.get('heading') or 0) % 360.0, 1), r=float(p.get('radius') or 0)))
    nodes, at = [], {}
    for n in root.iter('node'):
        at[int(n.get('index'))] = len(nodes)
        nodes.append([round(_dm(n.get('lat')), 6), round(_dm(n.get('lon')), 6)])
    names, ni, arcs, seen = [], {}, [], set()
    for a in root.iter('arc'):
        u, v = int(a.get('begin')), int(a.get('end'))
        if u not in at or v not in at or a.get('isPushBackRoute') == '1':
            continue
        nm = a.get('name') or ''
        key = (min(at[u], at[v]), max(at[u], at[v]), nm)
        if key in seen:
            continue
        seen.add(key)
        if nm not in ni:
            ni[nm] = len(names)
            names.append(nm)
        arcs.append([key[0], key[1], ni[nm]])
    runways = []
    tpath = os.path.join(os.path.dirname(path), icao + '.threshold.xml')
    if os.path.exists(tpath):
        for t in ET.parse(tpath).getroot().iter('threshold'):
            g = lambda k: (t.findtext(k) or '0').strip()
            runways.append(dict(n=g('rwy'), lat=round(float(g('lat')), 6), lon=round(float(g('lon')), 6), h=round(float(g('hdg-deg')), 2), displ=float(g('displ-m')), stopw=float(g('stopw-m'))))
    msg = dict(icao=icao, parking=parking, nodes=nodes, arcs=arcs, names=names, runways=runways)
    if len(json.dumps(msg, separators=(',', ':'))) > MAX_BYTES:
        raise ValueError('the ground network of %s is too big for the link' % icao)
    return msg


def dumps(msg):
    return json.dumps(msg, separators=(',', ':'))
