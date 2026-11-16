#!/usr/bin/env python3
"""The manual's tables and numbers, from the aircraft's own sources, so the manual cannot drift from the aircraft.

    python3 manual/mkmanual.py          writes manual/tab/*.tex; stops on anything that does not agree

- the control tables, from controls.md, checked against the station's page, the aircraft's menu and the camera
  dialog: a control that is there and not in controls.md stops the build, and so does one in controls.md that is gone;
- the alerts, from the aircraft's own list (fdm/onboard.py) and the station's (js/alerts.js, js/traffic.js), with
  what each means from ALERTS below: an alert with no entry stops the build;
- the limits and figures, from the flight laws' and the mission manager's constants and the data files;
- the performance tables, from the station's own table (gcs/js/perfdata.js, sampled from the flight model);
- the Hobbs and Lyall table, from hobbs_lyall.json: 114 guidelines, each with a status.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
TAB = os.path.join(HERE, 'tab')
sys.path.insert(0, os.path.join(ROOT, 'fdm'))
problems = []

# what each alert means and what the aircraft is doing about it, by the alert's id
ALERTS = {
    'engine': 'The engine has stopped. The aircraft has chosen the runway it reaches with the most height to spare and is gliding to it; it will circle over the approach to lose its surplus and land.',
    'no-site': 'The engine has stopped and no landing site of the plan is within the glide the aircraft counts on. It glides towards the nearest. A landing off a runway is not built.',
    'go-around': 'The landing was not begun: at the fix the aircraft was higher above the glide path than the capture takes over from. It circles over the fix down to the height the final is begun from, and lands when it can.',
    'missed-approach': 'The approach was not stable below 1,000 ft over the runway: off the line, off the glide path or off the approach speed by more than the gate allows for that height (150 ft over the runway: 60 ft, 45 ft and 15 kt under or 20 kt over), for two seconds. The aircraft climbs out straight ahead, flies a right-hand circuit and begins the landing again from the fix. Below 150 ft it is committed and lands.',
    'landing-abandoned': 'The approach broke the gate a third time. The aircraft climbs out and holds over the landing fix; it does not try again by itself. The operator decides: another approach, another runway or the engine-out site.',
    'crosswind': 'On the final the wind across the runway is over what the landing holds its limits to at this weight.',
    'structure': 'A load factor, airspeed or Mach limit has been passed. The flag stays until the flight ends.',
    'link': 'No station in control was heard for the time-out, and the aircraft left its plan for the lost-link route. It stays on it, link or no link, until told otherwise.',
    'nav-disagree': 'Two navigators in use differ by more than 3 deg. The aircraft takes the one whose bank agrees with its turn rate.',
    'nav-one': 'Fewer than two navigators are switched on: nothing is left to compare the attitude with.',
    'fuel-low': 'Less than the low-fuel figure is left.',
    'aoa': 'The angle of attack has been over its limit for half a second. The alert stands for at least 3 s and until the angle is back under the limit. The aircraft brings it back by itself: its pitch command is held down.',
    'aoa-near': 'The angle of attack has been within 0.15 deg of its limit for 3 s: closer than the approach is flown (0.2 to 0.3 deg under it at light weights). It clears when the angle has been more than 0.25 deg under the limit for 2 s.',
    'hold': 'The aircraft has stopped at a hold of its taxi route (a stop short of a runway it is to enter or cross, the line-up point for the takeoff, or a place the operator chose) and waits. It goes on only when the station in control clears that hold, by name, in the Clearances panel; it does not creep, and it stays where it is if the link is lost.',
    'gust': 'On the final, under 500 ft, the aircraft has lost 8 kt of speed or is sinking 8 ft/s more than the path or the flare asks (a loss of headwind, a downdraught), and the alert stands 4 s after the last time. It is raised whether or not the gust system is on: with it on, the aircraft is correcting (the nose held up, thrust added, more pitch in the flare); with it off, the landing may be hard.',
    'manual': 'The aircraft is being flown by hand from the station in control.',
    'off-plan': 'The aircraft has left its plan on a command (go to, hold, return home) and stays off it until Resume plan.',
    'no-link': 'This station is not hearing the aircraft. Raised by the station itself.',
    'link-restored': 'This station has the link again after losing it. Raised by the station; it stands for 20 s.',
    'traffic-warning': 'Another aircraft will be inside 0.75 nmi and 450 ft within 25 s. Raised by the station.',
    'traffic-caution': 'Another aircraft will be inside 0.75 nmi and 450 ft within 55 s. Raised by the station.',
    'traffic-advisory': 'Another aircraft will pass inside 1 nmi and 700 ft. Raised by the station.',
}


# two alerts whose words the aircraft puts together as it raises them: what the page then shows
SHOWN = {'manual': 'FLOWN BY HAND: PROTECTED or FLOWN BY HAND: DIRECT, NO PROTECTIONS', 'off-plan': 'OFF THE PLAN: GOTO, HOLD or HOME'}


def tex(s):
    s = str(s).replace('\\', '\x00')
    for a, b in (('&', r'\&'), ('%', r'\%'), ('_', r'\_'), ('#', r'\#'), ('$', r'\$'), ('{', r'\{'), ('}', r'\}'), ('~', r'\textasciitilde{}'), ('^', r'\textasciicircum{}')):
        s = s.replace(a, b)
    s = s.replace('\x00', r'\textbackslash{}')
    for a, b in (('…', r'\ldots{}'), ('◀', r'$\blacktriangleleft$'), ('▶', r'$\blacktriangleright$'), ('▲', r'$\blacktriangle$'), ('▼', r'$\blacktriangledown$'),
                 ('×', r'$\times$'), ('°', r'\textdegree{}'), ('"', "''"), ('<', r'\textless{}'), ('>', r'\textgreater{}'), ('²', r'\textsuperscript{2}')):
        s = s.replace(a, b)
    return s


def write(name, text):
    with open(os.path.join(TAB, name), 'w', encoding='utf-8') as fh:
        fh.write(text)


def table(spec, head, rows):
    body = [' & '.join(r'\textbf{%s}' % h for h in head) + r' \\', r'\midrule'] + [' & '.join(r) + r' \\' for r in rows]
    return '\\begin{tabularx}{\\textwidth}{@{}%s@{}}\n\\toprule\n%s\n\\bottomrule\n\\end{tabularx}\n' % (spec, '\n'.join(body))


RAGGED = r'>{\raggedright\arraybackslash}'


# ---------------------------------------------------------------------------------------------- controls
def controls():
    sections, head = {}, None
    for line in open(os.path.join(HERE, 'controls.md'), encoding='utf-8'):
        m = re.match(r'## (.+)', line)
        if m:
            head = m.group(1).strip()
            sections[head] = []
        elif line.startswith('|') and head and not re.match(r'\|\s*(id|Label|-)', line):
            sections[head].append([c.strip() for c in line.strip().strip('|').split('|')])
    page = open(os.path.join(ROOT, 'GlobalHawk', 'gcs', 'index.html'), encoding='utf-8').read()
    in_page = set(re.findall(r'<(?:button|input|select|canvas)[^>]*\bid="([^"]+)"', page))
    in_md = {r[0] for h, rows in sections.items() if len(rows[0]) == 3 for r in rows}
    for i in sorted(in_page - in_md):
        problems.append('a control of the page is not in controls.md: %s' % i)
    for i in sorted(in_md - in_page):
        problems.append('controls.md names a control the page does not have: %s' % i)
    menu = re.findall(r'<label>([^<]+)</label>', open(os.path.join(ROOT, 'GlobalHawk', 'GlobalHawk-set.xml'), encoding='utf-8').read())
    menu = [m for m in menu if m != 'Global Hawk']
    named = {r[0] for r in sections["The aircraft's menu in FlightGear"]}
    for m in menu:
        if m not in named:
            problems.append('a menu item is not in controls.md: %s' % m)
    for m in named - set(menu):
        problems.append('controls.md names a menu item that is gone: %s' % m)
    dialog = open(os.path.join(ROOT, 'GlobalHawk', 'gui', 'dialogs', 'globalhawk-camera.xml'), encoding='utf-8').read()
    buttons = [b for b in re.findall(r'<legend>([^<]+)</legend>', dialog)] + [b for b in re.findall(r'<label>([^<]+)</label>', dialog) if b in ('Latitude', 'Longitude', 'Keep the horizon level')]
    named = {r[0] for r in sections["The camera's dialog"]}
    for b in buttons:
        if b not in named:
            problems.append("a control of the camera's dialog is not in controls.md: %s" % b)
    for b in named - set(buttons):
        problems.append("controls.md names a control the camera's dialog does not have: %s" % b)
    n = 0
    for head, rows in sections.items():
        slug = re.sub(r'[^a-z]+', '', head.lower())
        if len(rows[0]) == 3:
            write('tab_ctl_%s.tex' % slug, table(RAGGED + 'p{38mm}' + RAGGED + 'X', ('Control', 'What it does'), [[r'\ann{%s}' % tex(r[1]), tex(r[2])] for r in rows]))
        else:
            write('tab_ctl_%s.tex' % slug, table(RAGGED + 'p{62mm}' + RAGGED + 'X', ('Item', 'What it does'), [[r'\ann{%s}' % tex(r[0]), tex(r[1])] for r in rows]))
        n += len(rows)
    return n


# ---------------------------------------------------------------------------------------------- alerts
def alerts():
    src = open(os.path.join(ROOT, 'fdm', 'onboard.py'), encoding='utf-8').read()
    rows = []
    for i, level, rest in re.findall(r"add\('([a-z-]+)', '(warning|caution|advisory)', (.+)\)\n", src):
        text = re.findall(r"'([A-Z][A-Z ,:]+[A-Z])'", rest)
        action = re.findall(r"'((?:[A-Z][a-z]|No )[^']*)'", rest)
        rows.append((i, level, ' or '.join(dict.fromkeys(t for t in text)) if text else '?', ' '.join(a.strip() for a in action)))
    js = open(os.path.join(ROOT, 'GlobalHawk', 'gcs', 'js', 'alerts.js'), encoding='utf-8').read()
    m = re.search(r"id: 'no-link', level: '(\w+)', text: '([^']+)', action: '([^']+)'", js)
    rows.append(('no-link', m.group(1), m.group(2), m.group(3)))
    js = open(os.path.join(ROOT, 'GlobalHawk', 'gcs', 'js', 'main.js'), encoding='utf-8').read()
    m = re.search(r"id: 'link-restored', level: '(\w+)', text: '([^']+)', action: s && s.link_lost \? '([^']+)'", js)
    rows.append(('link-restored', m.group(1), m.group(2), m.group(3)))
    js = open(os.path.join(ROOT, 'GlobalHawk', 'gcs', 'js', 'traffic.js'), encoding='utf-8').read()
    for level, text in re.findall(r"id: 'traffic', level: '(\w+)', text: '([^']+)'", js):
        rows.append(('traffic-' + level, level, text, 'Change height or route' if level != 'advisory' else 'Nothing to do yet'))
    order = dict(warning=0, caution=1, advisory=2)
    out = []
    for i, level, text, action in sorted(rows, key=lambda r: order[r[1]]):
        if i not in ALERTS:
            problems.append('an alert has no meaning in mkmanual.py: %s (%s)' % (i, text))
            continue
        fix = SHOWN.get(i, text)
        out.append([r'\ann{%s}' % tex(fix), level, tex(ALERTS[i]), tex(action.replace('%s', 'the site it names'))])
    for i in set(ALERTS) - {r[0] for r in rows}:
        problems.append('mkmanual.py explains an alert that is gone: %s' % i)
    write('tab_alerts.tex', table(RAGGED + 'p{36mm}l' + RAGGED + 'X' + RAGGED + 'p{38mm}', ('Alert', 'Level', 'What it means', 'What the page says to do'), out))
    return len(out)


# ---------------------------------------------------------------------------------------------- numbers
def numbers():
    import laws
    import missionmgr as MM
    import onboard
    g = json.load(open(os.path.join(ROOT, 'fdm', 'data', 'geometry.json')))
    mass = json.load(open(os.path.join(ROOT, 'fdm', 'data', 'mass.json')))
    e = json.load(open(os.path.join(ROOT, 'fdm', 'data', 'engine.json')))
    n = {}
    n['Span'], n['Length'], n['WingArea'] = '%.1f' % g['wing']['span'], '%.1f' % g['fuselage']['length'], '%.0f' % g['wing']['area_reference']
    n['Track'], n['Wheelbase'] = '%.1f' % g['gear']['main_track'], '%.1f' % g['gear']['wheelbase']
    pub = mass['published']
    n['Gross'], n['Empty'], n['Fuel'], n['NoFuel'] = ('{:,.0f}'.format(v) for v in (pub['gross'], pub['empty'], pub['fuel'], pub['gross'] - pub['fuel']))
    n['Rating'] = '{:,.0f}'.format(e['limits']['flat_rating_lbf'])
    n['MaxAlt'] = '{:,.0f}'.format(MM.MAX_ALT)
    n['BankLow'], n['BankHigh'] = '%.0f' % laws.BANK_LIMIT[0][1], '%.0f' % laws.BANK_LIMIT[-1][1]
    n['BankLowTo'], n['BankHighFrom'] = '{:,.0f}'.format(laws.BANK_LIMIT[1][0]), '{:,.0f}'.format(laws.BANK_LIMIT[2][0])
    n['BankCmd'] = '%.0f' % (100 * laws.BANK_COMMAND)
    n['AlphaLow'], n['AlphaCruise'] = '%.1f' % laws.ALPHA_LIMIT[0][1], '%.1f' % dict(laws.ALPHA_LIMIT)[0.6]
    n['FastKcas'] = '%.0f' % laws.FAST_KCAS
    n['FastMach'] = re.search(r'MACH_LIMIT = ([\d.]+)', open(os.path.join(ROOT, 'GlobalHawk', 'gcs', 'js', 'pfdmath.js')).read()).group(1)
    if 'nose up above Mach %s or' % n['FastMach'] not in open(os.path.join(ROOT, 'fdm', 'laws.py')).read():
        problems.append("the flight display's Mach limit is not the laws'")
    n['ScheduleKcas'], n['ScheduleMach'], n['ScheduleFrom'], n['ScheduleTop'] = '%.0f' % laws.SCHEDULE_KCAS, '%.2f' % laws.SCHEDULE[2][1], '{:,.0f}'.format(laws.SCHEDULE[1][0]), '{:,.0f}'.format(laws.SCHEDULE[2][0])
    n['NzMax'], n['NzMin'], n['LimitKeas'], n['LimitMach'], n['FailKeas'] = '%.1f' % laws.LIMIT_NZ[1], '%.1f' % laws.LIMIT_NZ[0], '%.0f' % laws.LIMIT_KEAS, '%.2f' % laws.LIMIT_MACH, '%.0f' % laws.FAIL_KEAS
    n['RotateKias'], n['RotatePitch'] = '%.0f' % laws.ROTATE_KIAS, '%.0f' % laws.ROTATE_PITCH
    n['GlideDeg'] = '%.2f' % __import__('math').degrees(__import__('math').atan(laws.GLIDE_TAN))
    n['ApproachCl'], n['FlarePitch'], n['FlareHeight'], n['Decel'] = '%.3f' % laws.APPROACH_CL, '%.1f' % laws.FLARE_PITCH, '%.0f' % laws.FLARE_HEIGHT, '%.3f' % laws.DECEL_G
    n['ManualPitchRate'], n['ManualBeta'] = '%.0f' % laws.MANUAL_PITCH_RATE, '%.0f' % laws.MANUAL_BETA
    n['GlideRatio'], n['InHand'], n['TurnCost'], n['HoldBank'], n['EntryHeight'] = '%.0f' % MM.GLIDE_RATIO, '{:,.0f}'.format(MM.IN_HAND), '%.0f' % MM.TURN_COST, '%.1f' % MM.HOLD_BANK, '{:,.0f}'.format(MM.ENTRY_HEIGHT)
    n['LinkTimeoutMin'], n['LinkTimeoutMax'] = '%.0f' % onboard.LINK_TIMEOUT_MIN, '%.0f' % onboard.LINK_TIMEOUT_MAX
    n['FuelLow'], n['OfferSec'], n['MinFinal'], n['MaxLeg'] = '{:,.0f}'.format(onboard.FUEL_LOW_LB), '%.0f' % onboard.OFFER_SEC, '%.0f' % onboard.MIN_FINAL_NM, '{:,.0f}'.format(onboard.MAX_LEG_NM)
    defaults = open(os.path.join(ROOT, 'GlobalHawk', 'Nasal', 'defaults.nas')).read()
    n['LinkTimeout'] = re.search(r'"ap/link-timeout-sec": (\d+)', defaults).group(1)
    hl = json.load(open(os.path.join(HERE, 'hobbs_lyall.json')))
    for status, key in (('met', 'HlMet'), ('partly', 'HlPartly'), ('not met', 'HlNot'), ('not applicable', 'HlNa')):
        n[key] = str(sum(h['status'] == status for h in hl))
    n['HlAll'] = str(len(hl))
    write('numbers.tex', ''.join('\\newcommand{\\M%s}{%s}\n' % (k, v) for k, v in n.items()))
    return n


# ---------------------------------------------------------------------------------------------- performance
def performance():
    s = open(os.path.join(ROOT, 'GlobalHawk', 'gcs', 'js', 'perfdata.js')).read()
    P = json.loads(re.search(r'const data = (\{.*\});', s).group(1))
    W = P['weight_lb']
    head = ['Height, ft'] + ['{:,.0f} lb'.format(w) for w in W]
    spec = 'l' + 'r' * len(W)
    num = lambda v, f='{:,.0f}': '--' if v is None else f.format(v)
    for key, name in (('climb_fpm', 'climb'), ('climb_pph', 'climbfuel'), ('level_pph', 'level'), ('descent_fpm', 'descent')):
        rows = [['{:,.0f}'.format(a)] + [num(v if not (key == 'climb_fpm' and v is not None and v < 50) else None) for v in P[key][i]] for i, a in enumerate(P['alt_ft'])]
        write('tab_perf_%s.tex' % name, '\\begin{tabular}{@{}%s@{}}\n\\toprule\n%s \\\\\n\\midrule\n%s\n\\bottomrule\n\\end{tabular}\n' % (
            spec, ' & '.join(head), '\n'.join(' & '.join(r) + r' \\' for r in rows)))
    write('tab_perf_speed.tex', '\\begin{tabular}{@{}lr@{}}\n\\toprule\nHeight, ft & KTAS \\\\\n\\midrule\n%s\n\\bottomrule\n\\end{tabular}\n' % '\n'.join(
        '{:,.0f} & {:.0f} \\\\'.format(a, v) for a, v in zip(P['alt_ft'], P['ktas'])))
    L = P['landing']
    rows = []
    for k, e in enumerate(L['elev_ft']):
        rows.append(['Touchdown, field at {:,.0f} ft'.format(e)] + ['{:,.0f}'.format(v) for v in L['touchdown_ft'][k]])
        rows.append(['Rollout ends'] + ['{:,.0f}'.format(v) for v in L['slow_ft'][k]])
        rows.append(['Runway to have'] + ['{:,.0f}'.format(round(1.15 * v, -2)) for v in L['slow_ft'][k]])
    write('tab_perf_landing.tex', '\\begin{tabular}{@{}%s@{}}\n\\toprule\n%s \\\\\n\\midrule\n%s\n\\bottomrule\n\\end{tabular}\n' % (
        'l' + 'r' * len(L['weight_lb']), ' & '.join(['Feet past the aiming point'] + ['{:,.0f} lb'.format(w) for w in L['weight_lb']]),
        '\n'.join(' & '.join(r) + r' \\' + ('\n\\addlinespace' if n % 3 == 2 and n < len(rows) - 1 else '') for n, r in enumerate(rows))))
    if abs(float(re.search(r'ROLL_MARGIN = ([\d.]+)', open(os.path.join(ROOT, 'GlobalHawk', 'gcs', 'js', 'predict.js')).read()).group(1)) - 1.15) > 1e-9:
        problems.append("the landing table's 15 % is no longer the station's ROLL_MARGIN")


# ---------------------------------------------------------------------------------------------- Hobbs and Lyall
def hobbs_lyall():
    hl = json.load(open(os.path.join(HERE, 'hobbs_lyall.json')))
    if len(hl) != 114 or len({h['code'] for h in hl}) != 114:
        problems.append('hobbs_lyall.json: %d guidelines, %d different codes; the study has 114' % (len(hl), len({h['code'] for h in hl})))
    for h in hl:
        if h['status'] not in ('met', 'partly', 'not met', 'not applicable') or not h['where'].strip():
            problems.append('hobbs_lyall.json: %s has no status or no reason' % h['code'])
    groups = {'1.1': 'Aircraft systems and automation', '1.2': 'Consumables', '1.3': 'The station itself', '1.5': 'The link', '1.6': 'Handing over control',
              '2.1': 'Location and flight path', '2.2': 'Terrain, airspace and weather', '2.4': 'The lost-link route', '2.5': 'Ending the flight',
              '3.1': 'Air traffic control', '3.2': 'Crew and ground support', '3.3': 'Other services'}
    key = lambda h: [int(x) for x in h['code'].split('_')[1].split('.')[:2]]
    mark = {'met': r'\textbf{met}', 'partly': 'partly', 'not met': r'\emph{not met}', 'not applicable': '--'}
    out, last = [], None
    for h in sorted(hl, key=lambda h: (key(h), 'TICP'.index(h['code'][0]), int(h['code'].rsplit('.', 1)[1]))):
        grp = '.'.join(h['code'].split('_')[1].split('.')[:2])
        if grp != last:
            out.append('\\addlinespace\\multicolumn{4}{@{}l}{\\textbf{%s}} \\\\' % tex(groups.get(grp, grp)))
            last = grp
        out.append('%s & %s & %s & %s \\\\' % (tex(h['code']), tex(h['guideline']), mark[h['status']], tex(h['where'])))
    spec = '@{}' + ''.join(RAGGED + 'p{%dmm}' % w for w in (12, 57, 13, 70)) + '@{}'
    # the whole table from here: TeX takes no \input inside a table before a rule
    write('tab_hl.tex', '\\begin{longtable}{%s}\n\\toprule\n\\textbf{Code} & \\textbf{Guideline} & \\textbf{Status} & \\textbf{In the station} \\\\\n\\midrule\n\\endhead\n%s\n\\bottomrule\n\\end{longtable}\n'
          % (spec, '\n'.join(out)))
    return len(hl)


if __name__ == '__main__':
    os.makedirs(TAB, exist_ok=True)
    nc, na, n, _, nh = controls(), alerts(), numbers(), performance(), hobbs_lyall()
    print('%d controls, %d alerts, %d numbers, %d guidelines' % (nc, na, len(n), nh))
    for p in problems:
        print('PROBLEM', p)
    sys.exit(1 if problems else 0)
