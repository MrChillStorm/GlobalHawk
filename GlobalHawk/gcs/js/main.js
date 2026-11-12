/**
 * The station: wires the link to the strip, the map and the commands.
 *
 *   index.html?host=localhost&port=5400&station=LRE&latency=0
 *
 * Every command is drawn or described first and sent only on "Send". It counts when the aircraft answers.
 */
(function () {
  'use strict';
  const G = window.GCS;
  const geo = G.geo;
  const $ = (id) => document.getElementById(id);
  const q = new URLSearchParams(location.search);
  const host = q.get('host') || (location.protocol.startsWith('http') ? location.hostname : 'localhost');
  const port = q.get('port') || (location.protocol.startsWith('http') && location.port ? location.port : '5400');
  const J = '/fdm/jsbsim/';
  const TELEMETRY = {
    lat: '/position/latitude-deg', lon: '/position/longitude-deg', alt: '/position/altitude-ft', hdg: '/orientation/heading-deg',
    kcas: '/velocities/airspeed-kt', gs: '/velocities/groundspeed-kt', vs: '/velocities/vertical-speed-fps', mach: '/velocities/mach',
    fuel: J + 'fuel/total-lbs', thr: J + 'ctl/throttle-norm',
    pitch: '/orientation/pitch-deg', roll: '/orientation/roll-deg', alpha: J + 'aero/alpha-deg', alphaLimit: J + 'ap/alpha-limit-deg',
    gamma: J + 'flight-path/gamma-deg', trackRad: J + 'flight-path/psi-gt-rad', udot: J + 'accelerations/udot-ft_sec2', vt: J + 'velocities/vt-fps',
    bankLimit: J + 'ap/bank-limit-deg', thrust: J + 'engine/thrust-lbf', ff: J + 'engine/fuel-flow-pph', failed: J + 'engine/failed',
    miscompare: J + 'nav/miscompare',
  };
  const TANKS = [['wing in L', 1736.5], ['wing in R', 1736.5], ['wing out L', 1557.3], ['wing out R', 1557.3], ['fus fwd', 5624.4], ['fus aft', 3088.0]];
  TANKS.forEach((t, i) => (TELEMETRY['tank' + i] = `${J}propulsion/tank[${i}]/contents-lbs`));
  const NAVS = [['kna', 'KN-A'], ['knb', 'KN-B'], ['lna', 'LN-A'], ['lnb', 'LN-B']];
  NAVS.forEach((n) => (TELEMETRY['nav_' + n[0]] = `${J}nav/${n[0]}-on`));
  const link = new G.Link({ transport: new G.WsTransport(host, port), station: q.get('station') || 'LRE', latency: Number(q.get('latency') || 0) });
  const map = new G.MapView($('map'));
  const pfd = new G.FlightDisplay($('pfd'));
  const alerts = new G.Alerts();
  $('tanks').innerHTML = TANKS.map((t, i) => `<div class="tank"><div class="bar"><i id="tank${i}"></i></div>${t[0]}</div>`).join('');
  $('navs').innerHTML = NAVS.map((n) => `<button id="nav-${n[0]}" data-nav="${n[0]}">${n[1]}</button>`).join('');
  NAVS.forEach((n) => $('nav-' + n[0]).addEventListener('click', () => {
    const on = !(tel['nav_' + n[0]] > 0.5);
    arm({ name: 'nav', button: null, ready: () => true, args: () => ({ name: n[0], on }), text: () => `Switch navigator ${n[1]} ${on ? 'ON' : 'OFF'}${on ? '' : ': the aircraft votes between those left on'}` });
  }));

  /* ------------------------------------------------------------- the tone: a second sense for warnings and cautions */
  let audio = null;
  let toneAt = 0;
  document.addEventListener('pointerdown', () => {
    if (!audio && (window.AudioContext || window.webkitAudioContext)) audio = new (window.AudioContext || window.webkitAudioContext)();
  }, { once: false });
  function beep(level) {
    if (!audio || audio.state !== 'running') return;
    const n = level === 'warning' ? 3 : 1;
    for (let i = 0; i < n; i++) {
      const o = audio.createOscillator();
      const g = audio.createGain();
      o.frequency.value = level === 'warning' ? 880 : 520;
      g.gain.value = 0.08;
      o.connect(g).connect(audio.destination);
      o.start(audio.currentTime + i * 0.18);
      o.stop(audio.currentTime + i * 0.18 + 0.12);
    }
  }
  const tel = {};
  let armed = null; // the command being prepared: { name, text, args(), preview, needsPoint, altField }
  let fitted = false;

  /* ------------------------------------------------------------- preparing a command */
  function arm(cmd) {
    armed = cmd;
    document.querySelectorAll('#commands button').forEach((b) => b.classList.remove('armed'));
    if (cmd && cmd.button) cmd.button.classList.add('armed');
    $('map').classList.toggle('aim', !!(cmd && cmd.needsPoint));
    renderConfirm();
  }

  function renderConfirm() {
    const box = $('confirm');
    if (!armed) {
      box.hidden = true;
      map.data.preview = null;
      map.draw();
      return;
    }
    box.hidden = false;
    $('confirm-text').textContent = armed.text();
    const extra = $('confirm-extra');
    if (armed.altField && !extra.firstChild) {
      extra.innerHTML = 'at <input type="number" id="alt-in" step="500" min="0" max="65000"> ft';
      $('alt-in').value = armed.alt;
      $('alt-in').addEventListener('input', () => {
        armed.alt = Number($('alt-in').value);
        renderConfirm();
      });
    } else if (!armed.altField) extra.innerHTML = '';
    $('confirm-yes').disabled = !armed.ready();
    map.data.preview = armed.preview ? armed.preview() : null;
    map.draw();
  }

  $('alerts').addEventListener('click', (e) => {
    const id = e.target.getAttribute && e.target.getAttribute('data-ack');
    if (id) alerts.acknowledge(id);
  });
  $('confirm-no').addEventListener('click', () => arm(null));
  $('confirm-yes').addEventListener('click', () => {
    if (!armed || !armed.ready()) return;
    link.command(armed.name, armed.args());
    arm(null);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') arm(null);
  });

  const here = () => (Number.isFinite(tel.lat) ? [tel.lat, tel.lon] : null);
  const fmtAlt = (ft) => Math.round(ft).toLocaleString('en-US');
  const targetAlt = () => (link.status && link.status.target ? link.status.target.alt_ft : Math.round((tel.alt || 20000) / 500) * 500);
  const eta = (ft) => (tel.gs > 30 ? `${Math.round(ft / geo.NM / tel.gs * 60)} min at the present ${Math.round(tel.gs)} kt` : '');

  function planSummary(p) {
    const kinds = p.items.map((i) => i.kind).join(', ');
    return `Send plan "${p.id || 'unnamed'}": ${kinds}; ${p.lost_link ? 'with' : 'NO'} lost-link route; ${(p.sites || []).length} landing site(s)`;
  }

  function armPlan(p, button) {
    arm({ name: 'plan', button, text: () => planSummary(p), ready: () => true, args: () => p, preview: () => ({ plan: p }) });
    const pts = [];
    geo.planLines(p.items, p.field && p.field.stand).forEach((l) => pts.push(...l.points));
    if (pts.length) map.fit(pts);
  }

  $('c-demo').addEventListener('click', () => {
    fetch('../Missions/demo-local.json').then((r) => r.json()).then((p) => armPlan(p, $('c-demo'))).catch(() => {
      $('conn').textContent = 'The demo plan could not be read from here (a page opened from a file cannot read other files): use "Plan file" and pick GlobalHawk/Missions/demo-local.json.';
    });
  });
  $('c-file').addEventListener('change', (e) => {
    const f = e.target.files[0];
    if (!f) return;
    f.text().then((t) => {
      try {
        armPlan(JSON.parse(t), null);
      } catch (err) {
        $('conn').textContent = 'That file is not a plan: ' + err.message;
      }
      e.target.value = '';
    });
  });
  $('c-start').addEventListener('click', () => arm({ name: 'start', button: $('c-start'), text: () => 'Start the plan: the aircraft taxis out and takes off by itself', ready: () => true, args: () => ({}) }));
  $('c-goto').addEventListener('click', () => {
    const c = { name: 'goto', button: $('c-goto'), needsPoint: true, altField: true, alt: targetAlt(), point: null };
    c.ready = () => !!c.point && c.alt >= 0 && c.alt <= 65000;
    c.text = () => {
      if (!c.point) return 'Go to: click the place on the map';
      const d = here() ? geo.course(here(), c.point) : null;
      return `Go to the point${d ? ` ${(d.ft / geo.NM).toFixed(1)} nmi away on ${Math.round(d.deg)}°${eta(d.ft) ? ', ' + eta(d.ft) : ''}` : ''}, then hold over it`;
    };
    c.args = () => ({ lat: c.point[0], lon: c.point[1], alt_ft: c.alt });
    c.preview = () => (c.point ? { line: here() ? [here(), c.point] : null, circle: { centre: c.point, radiusFt: holdRadius() }, at: c.point, label: `hold ${fmtAlt(c.alt)} ft` } : null);
    arm(c);
  });
  $('c-hold').addEventListener('click', () => arm({
    name: 'hold', button: $('c-hold'), ready: () => true, args: () => ({}),
    text: () => `Hold here at ${fmtAlt(targetAlt())} ft: a right-hand circle starting from the present position`,
    preview: () => (here() ? { circle: { centre: geo.along(here(), tel.hdg + 90, holdRadius()), radiusFt: holdRadius() } } : null),
  }));
  $('c-alt').addEventListener('click', () => {
    const c = { name: 'altitude', button: $('c-alt'), altField: true, alt: targetAlt() };
    c.ready = () => c.alt >= 0 && c.alt <= 65000;
    c.text = () => `${c.alt > (tel.alt || 0) + 150 ? 'Climb to' : c.alt < (tel.alt || 0) - 150 ? 'Descend to' : 'Stay at'} the height below (now ${fmtAlt(tel.alt || 0)} ft)`;
    c.args = () => ({ alt_ft: c.alt });
    arm(c);
  });
  $('c-resume').addEventListener('click', () => arm({ name: 'resume', button: $('c-resume'), ready: () => true, args: () => ({}), text: () => 'Go back to the plan, to the leg that was left' }));
  $('c-home').addEventListener('click', () => arm({
    name: 'home', button: $('c-home'), ready: () => true, args: () => ({}),
    text: () => 'Return home now along the lost-link route, and land',
    preview: () => (link.plan && link.plan.lost_link ? { plan: { items: link.plan.lost_link }, line: here() && link.plan.lost_link[0].points ? [here(), link.plan.lost_link[0].points[0]] : null } : null),
  }));

  /** The radius the aircraft will hold at: 11.5 deg of bank at the present ground speed (fdm/missionmgr.py). */
  function holdRadius() {
    const v = Math.max((tel.gs || 200) * 1.6878, 100);
    return (v * v) / (32.174 * Math.tan((11.5 * Math.PI) / 180));
  }

  map.onClick = (p) => {
    if (armed && armed.needsPoint) {
      armed.point = p;
      renderConfirm();
    }
  };
  $('follow').addEventListener('click', () => {
    map.follow = !map.follow;
    render();
  });
  $('fit').addEventListener('click', () => {
    const p = link.plan;
    if (!p) return;
    const pts = [];
    geo.planLines(p.items, p.field && p.field.stand).forEach((l) => pts.push(...l.points));
    if (here()) pts.push(here());
    map.fit(pts);
    render();
  });

  /* ------------------------------------------------------------- showing */
  function render() {
    const s = link.status;
    const live = link.state.mode === 'live' && link.lastDown !== null && Date.now() - link.lastDown < 3000 + link.latency;
    $('doing').textContent = !live ? 'no connection' : s ? s.doing : 'waiting for the aircraft';
    $('doing').style.color = s && s.contingency ? 'var(--lost)' : '';
    $('next').textContent = live && s ? s.next + (s.off_plan ? `   (off the plan: ${s.off_plan})` : '') : '';
    $('alt').textContent = Number.isFinite(tel.alt) ? fmtAlt(tel.alt) : '-';
    $('kcas').textContent = Number.isFinite(tel.kcas) ? Math.round(tel.kcas) : '-';
    const flying = live && s && s.started && s.target && !['taxi', 'takeoff', 'done'].includes(s.kind); // on the ground there is no target to show
    $('alt-cmd').textContent = flying ? '→ ' + fmtAlt(s.target.alt_ft) : '';
    $('kcas-cmd').textContent = flying ? '→ ' + Math.round(s.target.kcas) : '';
    const chip = $('link');
    const sending = live && link.beating; // hearing the aircraft is not enough: it must be hearing this station
    chip.className = 'chip ' + (sending ? 'live' : live || link.state.mode === 'connecting' ? 'connecting' : 'down');
    chip.textContent = sending ? `${link.station} linked` : live ? 'receiving only' : link.state.mode === 'connecting' ? 'connecting' : 'NO LINK';
    const timeout = s ? s.link_timeout : 30;
    $('link-note').textContent = live
      ? `${link.latency ? link.latency / 1000 + ' s delay · ' : ''}if lost: route home after ${timeout} s`
      : s && s.started ? `the aircraft goes home by itself ${timeout} s after the last contact` : '';
    $('n-hdg').textContent = Number.isFinite(tel.hdg) ? String(Math.round(tel.hdg) % 360).padStart(3, '0') + '°' : '-';
    $('n-mach').textContent = Number.isFinite(tel.mach) ? tel.mach.toFixed(3) : '-';
    $('n-gs').textContent = Number.isFinite(tel.gs) ? Math.round(tel.gs) + ' kt' : '-';
    $('n-vs').textContent = Number.isFinite(tel.vs) ? (tel.vs * 60 >= 0 ? '+' : '') + Math.round(tel.vs * 6) * 10 : '-';
    $('n-fuel').textContent = Number.isFinite(tel.fuel) ? fmtAlt(tel.fuel) : '-';
    $('n-thr').textContent = Number.isFinite(tel.thr) ? Math.round(tel.thr * 100) + ' %' : '-';
    // one list: the aircraft's alerts and the station's own, ranked, each with what to do
    const list = alerts.update(s ? s.alerts : [], link.lastDown, !!(s && s.started) || link.lastDown !== null);
    const html = list.map((a) => `<div class="alert ${a.level} ${a.acked ? 'acked' : 'new'}"><b>${esc(a.text)}</b><span class="do">${esc(a.action)}</span>${a.acked ? '' : `<button data-ack="${esc(a.id)}">OK</button>`}</div>`).join('');
    if ($('alerts').dataset.html !== html) {
      $('alerts').innerHTML = html;
      $('alerts').dataset.html = html;
    }
    const tone = alerts.tone();
    if (tone && Date.now() - toneAt > (tone === 'warning' ? 2000 : 5000)) {
      toneAt = Date.now();
      beep(tone);
    }
    // the flight display
    pfd.draw({
      pitch: tel.pitch, roll: tel.roll, hdg: tel.hdg, track: Number.isFinite(tel.trackRad) ? (tel.trackRad * 180) / Math.PI : NaN, gamma: tel.gamma,
      kcas: tel.kcas, mach: tel.mach, alt: tel.alt, vs: tel.vs, alpha: tel.alpha, alphaLimit: tel.alphaLimit, vt: tel.vt, udot: tel.udot, bankLimit: tel.bankLimit,
      target: flying ? s.target : null, course: flying && s.leg ? geo.course(s.leg[0], s.leg[1]).deg : NaN,
      mode: live && s ? s.doing : 'NO LINK', caution: !live || !!(s && s.contingency),
    });
    // engine, fuel, navigators
    const dead = tel.failed > 0.5;
    $('e-state').textContent = Number.isFinite(tel.failed) ? (dead ? 'FAILED' : 'running') : '-';
    $('e-state').className = dead ? 'bad' : '';
    $('e-thrust').textContent = Number.isFinite(tel.thrust) ? fmtAlt(tel.thrust) : '-';
    $('e-ff').textContent = Number.isFinite(tel.ff) ? fmtAlt(tel.ff) : '-';
    $('e-hours').textContent = tel.ff > 20 && Number.isFinite(tel.fuel) ? (tel.fuel / tel.ff).toFixed(1) + ' h at this flow' : '-';
    TANKS.forEach((t, i) => {
      const v = tel['tank' + i];
      $('tank' + i).style.height = Number.isFinite(v) ? Math.max(0, Math.min(100, (100 * v) / t[1])) + '%' : '0';
      $('tank' + i).parentNode.title = Number.isFinite(v) ? `${Math.round(v)} of ${Math.round(t[1])} lb` : '';
    });
    NAVS.forEach((n) => {
      const on = tel['nav_' + n[0]] > 0.5;
      const b = $('nav-' + n[0]);
      b.classList.toggle('off', !on);
      b.textContent = `${n[1]} ${on ? 'on' : 'OFF'}`;
      b.disabled = !live;
    });
    $('nav-note').textContent = tel.miscompare > 0.5 ? '· two disagree' : '';
    // which commands make sense now
    const enroute = !!(live && s && s.started && (s.kind === 'route' || s.kind === 'hold'));
    $('c-start').disabled = !(live && s && s.plan && !s.started);
    $('c-demo').disabled = !live;
    $('c-goto').disabled = $('c-hold').disabled = $('c-alt').disabled = !enroute;
    $('c-resume').disabled = !(live && s && s.off_plan && s.contingency !== 'engine' && s.kind !== 'done');
    $('c-home').disabled = !(enroute && link.plan && link.plan.lost_link);
    $('follow').classList.toggle('on', map.follow);
    // sent commands and the aircraft's notes
    $('log').innerHTML = link.commands.slice(-8).reverse().map((c) => {
      const label = { sent: 'sent…', accepted: 'accepted', rejected: 'REJECTED', 'no answer': 'NO ANSWER' }[c.state];
      return `<li><span class="when">${clock(c.sentAt)}</span><span>${esc(c.name)}${c.reason ? `<div class="why">${esc(c.reason)}</div>` : ''}</span><span class="st ${c.state.split(' ')[0]}">${label}</span></li>`;
    }).join('');
    $('events').innerHTML = (s ? s.events.slice().reverse() : []).map((e) => `<li><span class="when">${mmss(e[0])}</span><span>${esc(e[1])}</span></li>`).join('');
    $('conn').textContent = $('conn').textContent.startsWith('The demo') || $('conn').textContent.startsWith('That file') ? $('conn').textContent : `${link.state.message || ''}`;
    map.data.plan = link.plan;
    map.data.status = live ? s : null;
    map.data.airborne = enroute;
    map.data.lostLabel = `if the link is lost: after ${timeout} s`;
    map.draw();
  }

  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const clock = (ms) => new Date(ms).toTimeString().slice(3, 8);
  const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

  const byPath = {};
  Object.keys(TELEMETRY).forEach((k) => (byPath[TELEMETRY[k]] = k));
  link.on((what, data) => {
    if (what === 'value' && byPath[data]) {
      tel[byPath[data]] = Number(link.values[data]);
      if (Number.isFinite(tel.lat) && Number.isFinite(tel.lon)) {
        map.setAircraft(tel.lat, tel.lon, tel.hdg || 0);
        if (!fitted) {
          fitted = true;
          map.ftPerPx = 400;
        }
      }
    }
    if (what === 'command' && armed) renderConfirm();
  });
  window.addEventListener('resize', () => map.resize());
  map.resize();
  link.start(Object.values(TELEMETRY));
  setInterval(() => {
    if (armed) renderConfirm();
    render();
  }, 250);
  window.GCSApp = { link, map, tel, pfd, alerts }; // for looking at from the console
})();
