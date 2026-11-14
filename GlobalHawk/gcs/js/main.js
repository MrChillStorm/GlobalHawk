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
    agl: '/position/altitude-agl-ft',
    kcas: '/velocities/airspeed-kt', gs: '/velocities/groundspeed-kt', vs: '/velocities/vertical-speed-fps', mach: '/velocities/mach',
    fuel: J + 'fuel/total-lbs', thr: J + 'ctl/throttle-norm',
    pitch: '/orientation/pitch-deg', roll: '/orientation/roll-deg', alpha: J + 'aero/alpha-deg', alphaLimit: J + 'ap/alpha-limit-deg',
    gamma: J + 'flight-path/gamma-deg', trackRad: J + 'flight-path/psi-gt-rad', udot: J + 'accelerations/udot-ft_sec2', vt: J + 'velocities/vt-fps',
    bankLimit: J + 'ap/bank-limit-deg', thrust: J + 'engine/thrust-lbf', ff: J + 'engine/fuel-flow-pph', failed: J + 'engine/failed',
    miscompare: J + 'nav/miscompare', weight: J + 'inertia/weight-lbs',
  };
  const TANKS = [['wing in L', 1736.5], ['wing in R', 1736.5], ['wing out L', 1557.3], ['wing out R', 1557.3], ['fus fwd', 5624.4], ['fus aft', 3088.0]];
  TANKS.forEach((t, i) => (TELEMETRY['tank' + i] = `${J}propulsion/tank[${i}]/contents-lbs`));
  const NAVS = [['kna', 'KN-A'], ['knb', 'KN-B'], ['lna', 'LN-A'], ['lnb', 'LN-B']];
  NAVS.forEach((n) => (TELEMETRY['nav_' + n[0]] = `${J}nav/${n[0]}-on`));
  const demo = q.get('demo') === '1';
  const station = q.get('station') || 'LRE';
  // over a satellite everything is late: 1.2 s each way is an assumed round figure for an MCE, none for the others
  const latency = q.get('latency') !== null ? Number(q.get('latency')) : station === 'MCE' ? 1200 : 0;
  const demoSpeed = Math.max(1, Number(q.get('speed') || 1));
  const aircraft = demo ? new G.DemoAircraft({ speed: demoSpeed }) : null; // ?demo=1: a stand-in in this page
  const link = new G.Link({ transport: aircraft || new G.WsTransport(host, port), station, latency });
  const map = new G.MapView($('map'));
  // the map's layers: which are shown and why (js/layers.js, js/overlayctx.js, js/overlays.js)
  const storage = (() => {
    try {
      return window.localStorage;
    } catch (e) {
      return null;
    }
  })();
  const layers = new G.layers.Layers({ storage, key: 'gcs.layers' });
  G.overlayctx.defineLayers(layers);
  const savedLayers = layers.load() || {};
  layers.applyQuery(q.get('layers'));
  const ov = new G.Overlays({
    map, layers, demo, fetch: (u, o) => window.fetch(u, o), store: new G.store.Store('gcs-data'),
    awc: q.get('awc'), tiles: q.get('tiles'), sourcesBase: q.get('sources'), offline: q.get('offline') === '1',
    prefs: Object.assign({}, savedLayers.prefs || {}, q.get('base') ? { base: q.get('base') } : {}),
    panel: { button: $('layers-btn'), declutter: $('declutter-btn'), chips: $('chips'), box: $('layers-panel') },
  });
  const pfd = new G.FlightDisplay($('pfd'));
  const alerts = new G.Alerts();
  let trafficList = []; // other aircraft, from FlightGear's AI and multiplayer tree
  function pollTraffic() {
    if (demo) {
      trafficList = aircraft.traffic();
      return;
    }
    if (link.state.mode !== 'live') return;
    fetch(`http://${host}:${port}/json/ai/models?d=3`, { cache: 'no-store' }).then((r) => r.json()).then((tree) => {
      trafficList = G.traffic.parse(tree);
    }).catch(() => {});
  }
  setInterval(pollTraffic, 2000);
  const forecast = G.predict.make(G.perfdata);
  ov.forecast = forecast;
  let editor = null; // the plan being edited, or null
  const hms = (s) => {
    const min = Math.round(s / 60); // whole minutes first: 1 h 59.6 min is 2 h 00 min, never "1 h 60 min"
    return min >= 60 ? `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')} min` : `${min} min`;
  };
  /** The aircraft as the forecast takes it: now if flying, else full of what it has on the field. */
  const stateNow = (elev) => ({ alt_ft: Number.isFinite(tel.alt) ? tel.alt : elev, weight_lb: Number.isFinite(tel.weight) ? tel.weight : 25600, fuel_lb: Number.isFinite(tel.fuel) ? tel.fuel : 14150 });
  $('tanks').innerHTML = TANKS.map((t, i) => `<div class="tank"><div class="bar"><i id="tank${i}"></i></div>${t[0]}</div>`).join('');
  $('navs').innerHTML = NAVS.map((n) => `<button id="nav-${n[0]}" data-nav="${n[0]}">${n[1]}</button>`).join('');
  NAVS.forEach((n) => $('nav-' + n[0]).addEventListener('click', () => {
    const on = !(tel['nav_' + n[0]] > 0.5);
    arm({ name: 'nav', button: null, ready: () => true, args: () => ({ name: n[0], on }), text: () => `Switch navigator ${n[1]} ${on ? 'ON' : 'OFF'}${on ? '' : ': the aircraft votes between those left on'}` });
  }));

  /* ------------------------------------------------------------- the demo's own controls */
  $('demobar').hidden = !demo;
  if (demo) {
    $('d-speed').textContent = demoSpeed > 1 ? `running ${demoSpeed} times as fast as the clock` : 'add &speed=10 to the address to run it faster';
    $('d-engine').addEventListener('click', () => {
      aircraft.send('/fdm/jsbsim/engine/failed', 1);
      $('d-engine').disabled = true;
    });
    $('d-link').addEventListener('click', () => {
      if (link.beating) link.stop();
      else link.start([]);
      $('d-link').textContent = link.beating ? 'Cut the link' : 'Restore the link';
    });
  }

  /* ------------------------------------------------------------- who has control, and handing it over */
  const ticked = (id) => [...$(id).querySelectorAll('input[type=checkbox]')].every((b) => b.checked);
  const untick = (id) => $(id).querySelectorAll('input[type=checkbox]').forEach((b) => (b.checked = false));
  $('ctl-offer-go').addEventListener('click', () => {
    link.command('control.offer', { to: $('ctl-to').value });
    untick('ctl-offer');
  });
  $('ctl-cancel').addEventListener('click', () => link.command('control.cancel'));
  $('ctl-accept-go').addEventListener('click', () => {
    link.command('control.accept');
    untick('ctl-accept');
  });
  $('ctl-take').addEventListener('click', () => link.command('control.take'));
  function renderControl(s, live) {
    const c = s && s.control;
    const mine = link.inControl();
    const st = $('ctl-state');
    st.className = 'mid ' + (mine ? 'mine' : 'theirs');
    st.textContent = !live || !c ? '-' : mine ? `${station} has control` : c.holder ? `watching: ${c.holder} has control` : 'nobody has control yet';
    document.body.classList.toggle('watching', live && !mine);
    const others = c ? c.stations.filter((x) => x.name !== station && x.age < 10).map((x) => x.name) : [];
    const sel = $('ctl-to');
    if (sel.dataset.list !== others.join(',')) {
      sel.innerHTML = others.map((n) => `<option>${esc(n)}</option>`).join('');
      sel.dataset.list = others.join(',');
    }
    $('ctl-offer').hidden = !(live && mine && !c.offer_to && others.length);
    $('ctl-offer-go').disabled = !ticked('ctl-offer');
    $('ctl-offered').hidden = !(live && mine && c.offer_to);
    $('ctl-offered-text').textContent = c && c.offer_to ? `Control is offered to ${c.offer_to}: waiting for them to accept.` : '';
    $('ctl-accept').hidden = !(live && !mine && c && c.offer_to === station);
    $('ctl-accept-go').disabled = !ticked('ctl-accept');
    $('ctl-take').hidden = !(live && !mine && c && c.holder && s.link_lost);
    return mine;
  }

  let inputNow = 'keyboard';
  /* ------------------------------------------------------------- flying by hand: gamepad or keys, sent as the stick */
  let stickNow = null; // { p, r, y, t, s } while the aircraft is flown by hand from this station
  let stickAt = 0;
  const keysDown = new Set();
  const FLY_KEYS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'q', 'e', 'w', 's', 'z', 'x'];
  document.addEventListener('keydown', (e) => {
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (stickNow && FLY_KEYS.includes(k) && e.target.tagName !== 'INPUT') {
      keysDown.add(k);
      e.preventDefault();
    }
  });
  document.addEventListener('keyup', (e) => keysDown.delete(e.key.length === 1 ? e.key.toLowerCase() : e.key));
  window.addEventListener('blur', () => keysDown.clear());
  function flyByHand() {
    const s = link.status;
    const on = !!(s && s.manual > 0 && link.inControl());
    if (on && !stickNow) stickNow = { p: 0, r: 0, y: 0, t: Number.isFinite(tel.thr) ? tel.thr : 0.5, s: 0 };
    if (!on) stickNow = null;
    $('stickbox').hidden = !on;
    if (!on) return;
    const now = performance.now();
    const dt = Math.min(0.2, (now - stickAt) / 1000);
    stickAt = now;
    const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter((p) => p && p.connected) : [];
    const pad = pads[0];
    inputNow = pad ? 'gamepad: ' + pad.id.slice(0, 28) : 'keyboard';
    stickNow = pad && !keysDown.size ? G.controls.fromGamepad(pad.axes, pad.buttons, stickNow, dt) : G.controls.fromKeys(keysDown, stickNow, dt);
    link.stick(stickNow);
    const x = $('stick').getContext('2d');
    x.clearRect(0, 0, 110, 110);
    x.strokeStyle = '#243040';
    x.beginPath();
    x.moveTo(55, 0);
    x.lineTo(55, 110);
    x.moveTo(0, 55);
    x.lineTo(110, 55);
    x.stroke();
    x.fillStyle = '#3fd0ff';
    x.beginPath();
    x.arc(55 + stickNow.r * 50, 55 - stickNow.p * 50, 6, 0, 2 * Math.PI); // stick forward is up
    x.fill();
    $('stick-text').innerHTML = `${pad ? 'gamepad: ' + esc(pad.id.slice(0, 28)) : 'keys: arrows stick, Q E pedals, W S throttle, Z X spoilers'}<br>throttle ${Math.round(stickNow.t * 100)} %, spoilers ${Math.round(stickNow.s * 100)} %, pedals ${stickNow.y.toFixed(1)}${link.latency ? `<br>everything arrives ${link.latency / 1000} s late` : ''}`;
  }
  setInterval(flyByHand, 50);
  const armManual = (mode, button, text) => button.addEventListener('click', () => arm({ name: 'manual', button, ready: () => true, args: () => ({ mode }), text: () => text }));
  armManual(0, $('m-auto'), 'Automatic: the aircraft takes over and holds where it is; Resume plan takes it back to the plan');
  armManual(1, $('m-prot'), 'Fly by hand, PROTECTED: the stick asks for pitch rate and bank angle, the aircraft keeps its limits. It goes back to automatic by itself if the link is lost');
  armManual(2, $('m-direct'), 'Fly by hand, DIRECT: the surfaces follow the stick, with damping only. NO LIMITS: the aircraft can be stalled or overstressed');

  /* ------------------------------------------------------------- the tone: a second sense for warnings and cautions */
  let audio = null;
  let toneAt = 0;
  document.addEventListener('pointerdown', () => {
    if (!audio && (window.AudioContext || window.webkitAudioContext)) audio = new (window.AudioContext || window.webkitAudioContext)();
  }, { once: false });
  function beep(level) {
    if (!audio || audio.state !== 'running') return;
    // the loss of the link: two notes in turn, which no other alert uses; a warning three high beeps; a caution one low
    const n = level === 'link' ? 4 : level === 'warning' ? 3 : 1;
    if (level === 'message') {
      const o = audio.createOscillator();
      const g = audio.createGain();
      o.frequency.value = 660;
      g.gain.value = 0.04;
      o.connect(g).connect(audio.destination);
      o.start(audio.currentTime);
      o.stop(audio.currentTime + 0.09);
      return;
    }
    for (let i = 0; i < n; i++) {
      const o = audio.createOscillator();
      const g = audio.createGain();
      o.frequency.value = level === 'link' ? (i % 2 ? 392 : 740) : level === 'warning' ? 880 : 520;
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
    } else if (armed.secField && !extra.firstChild) {
      extra.innerHTML = 'time-out <input type="number" id="sec-in" step="5" min="10" max="300"> s';
      $('sec-in').value = armed.sec;
      $('sec-in').addEventListener('input', () => {
        armed.sec = Number($('sec-in').value);
        renderConfirm();
      });
    } else if (!armed.altField && !armed.secField) extra.innerHTML = '';
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
    const after = armed.sent;
    arm(null);
    if (after) after();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') arm(null);
  });

  const here = () => (Number.isFinite(tel.lat) ? [tel.lat, tel.lon] : null);
  const fmtAlt = (ft) => Math.round(ft).toLocaleString('en-US');
  const targetAlt = () => (link.status && link.status.target ? link.status.target.alt_ft : Math.round((tel.alt || 20000) / 500) * 500);
  /** Forecast of flying from here to a point at a height, and of going home from there by the lost-link route. */
  function forecastTo(pt, alt) {
    if (!here()) return null;
    const there = forecast.predict([{ dist_ft: geo.course(here(), pt).ft, alt_ft: alt, name: 'go-to point' }], stateNow(0));
    const out = { t_s: there.total.t_s, fuel_lb: there.points[0].fuel_lb, warnings: there.warnings.slice(), home: null };
    const p = link.plan;
    if (p && p.lost_link) {
      const st = stateNow(0);
      const back = forecast.predict(G.plancheck.legs(p.lost_link, pt, p.field), { alt_ft: there.points[0].alt_ft, weight_lb: st.weight_lb - there.total.fuel_used_lb, fuel_lb: there.points[0].fuel_lb });
      out.home = { t_s: back.total.t_s, fuel_lb: back.points[back.points.length - 1].fuel_lb, warnings: back.warnings };
    }
    return out;
  }

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
    // the copy that ships in js/demoplan.js is the same plan: a page opened from a file cannot read the Missions folder
    const builtin = () => armPlan(JSON.parse(JSON.stringify(G.demoplan)), $('c-demo'));
    if (demo || location.protocol === 'file:') builtin();
    else fetch('../Missions/demo-local.json').then((r) => r.json()).then((p) => armPlan(p, $('c-demo'))).catch(builtin);
  });
  $('c-here').addEventListener('click', () => {
    // for an airport FlightGear started it at: the aircraft stands lined up on a runway, and the plan is laid from there
    if (!here() || !Number.isFinite(tel.hdg) || !Number.isFinite(tel.alt)) return;
    const elev = tel.alt - (Number.isFinite(tel.agl) ? tel.agl : 5);
    armPlan(geo.localPlan(here(), tel.hdg, elev), $('c-here'));
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
      const f = forecastTo(c.point, c.alt);
      const more = f ? `: there in ${hms(f.t_s)} with ${fmtAlt(f.fuel_lb)} lb${f.home ? `; going home from there, ${fmtAlt(Math.max(0, f.home.fuel_lb))} lb left on landing${f.home.fuel_lb < G.predict.RESERVE_LB ? ' (UNDER THE RESERVE)' : ''}` : ''}${f.warnings.length ? '. ' + f.warnings.join('; ') : ''}` : '';
      return `Go to the point${d ? ` ${(d.ft / geo.NM).toFixed(1)} nmi away on ${Math.round(d.deg)}°` : ''}, then hold over it${more}`;
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
  $('c-timeout').addEventListener('click', () => {
    const now = link.status ? link.status.link_timeout : 30;
    arm({
      name: 'linktimeout', button: $('c-timeout'), secField: true, sec: now,
      ready: () => G.linkinfo.validTimeout(armed.sec) !== null,
      text: () => `Lost-link time-out ${Number.isFinite(armed.sec) ? armed.sec : '?'} s (it is ${now} s now): after that long without hearing the station in control the aircraft leaves its plan and flies its lost-link route home. ${G.linkinfo.validTimeout(armed.sec) === null ? `The aircraft takes ${G.linkinfo.TIMEOUT_MIN} to ${G.linkinfo.TIMEOUT_MAX} s.` : ''}`,
      args: () => ({ sec: armed.sec }),
    });
  });
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
    text: () => {
      const p = link.plan;
      if (!p || !p.lost_link || !here()) return 'Return home now along the lost-link route, and land';
      const r = forecast.predict(G.plancheck.legs(p.lost_link, here(), p.field), stateNow(0));
      const roll = landingWords(r, p.field);
      return `Return home now along the lost-link route, and land: on the ground in ${hms(r.total.t_s)} with ${fmtAlt(Math.max(0, r.points[r.points.length - 1].fuel_lb))} lb${roll ? '; ' + roll : ''}`;
    },
    preview: () => (link.plan && link.plan.lost_link ? { plan: { items: link.plan.lost_link }, line: here() && link.plan.lost_link[0].points ? [here(), link.plan.lost_link[0].points[0]] : null } : null),
  }));

  /** The radius the aircraft will hold at: 11.5 deg of bank at the present ground speed (fdm/missionmgr.py). */
  function holdRadius() {
    const v = Math.max((tel.gs || 200) * 1.6878, 100);
    return (v * v) / (32.174 * Math.tan((11.5 * Math.PI) / 180));
  }

  /* ------------------------------------------------------------- the belly camera (the sensor operator's) */
  let aiming = false; // the next click on the map is the point the camera locks on
  const aim = (on) => {
    aiming = on;
    $('cam-point').classList.toggle('armed', on);
    $('map').classList.toggle('aim', on || !!(armed && armed.needsPoint));
  };
  $('cam-point').addEventListener('click', () => aim(!aiming));
  $('cam-nearest').addEventListener('click', () => link.camera('nearest'));
  $('cam-unlock').addEventListener('click', () => link.camera('unlock'));
  $('cam-level').addEventListener('click', () => link.camera(G.camera.state(link.values).level ? 'level off' : 'level'));
  [['cam-left', -1, 0], ['cam-right', 1, 0], ['cam-up', 0, 1], ['cam-down', 0, -1]].forEach(([id, r, u]) => $(id).addEventListener('click', () => link.cameraSlew(r, u)));

  // "just click anything on the map": a click that no command and no plan edit asked for locks the belly camera on what is
  // there (an aircraft at its height, a landing site, a route point, an airfield) or on the place itself. A switch in the
  // Camera panel turns it off; it is kept in the browser. Not a flight command: it needs no control and gets no answer.
  let camClick = true;
  try {
    camClick = localStorage.getItem('gcs.camclick') !== '0';
  } catch (e) { /* no storage: it stays on */ }
  $('cam-click').checked = camClick;
  $('cam-click').addEventListener('change', () => {
    camClick = $('cam-click').checked;
    try {
      localStorage.setItem('gcs.camclick', camClick ? '1' : '0');
    } catch (e) { /* the choice then lasts until the page closes */ }
  });
  function lockCameraAt(p, screen) {
    const hit = screen ? map.pickAt(screen.x, screen.y) : null;
    const at = hit ? hit.p : p;
    link.camera(G.camera.point(at, hit && hit.kind === 'aircraft' ? hit.alt_ft : undefined));
    map.flash(at, hit ? `camera → ${hit.name}` : 'camera → here');
  }
  map.onClick = (p, screen) => {
    if (aiming) {
      link.camera(G.camera.point(p));
      aim(false);
    } else if (armed && armed.needsPoint) {
      armed.point = p;
      renderConfirm();
    } else if (editor && !armed) {
      editor.add(p);
      renderEditor();
    } else if (camClick && !armed && !demo && link.state.mode === 'live') {
      lockCameraAt(p, screen);
    }
  };
  map.onHandle = (i, p, done) => {
    if (!editor) return;
    editor.selected = i;
    if (p) editor.move(i, p);
    renderEditor();
  };

  /** A forecast's landing in words: the weight, the rollout, the runway to have, and whether the plan's runway is enough. */
  function landingWords(r, field) {
    const pt = r.points[r.points.length - 1];
    if (!pt || !pt.landing) return '';
    const L = pt.landing;
    const hundred = (v) => fmtAlt(Math.round(v / 100) * 100);
    const have = field && Number(field.runway_past_aim_ft) > 0 ? Number(field.runway_past_aim_ft) : null;
    const verdict = have === null ? 'the plan does not say how much there is' : L.runway_ft > have ? `MORE THAN THE ${fmtAlt(have)} ft THE PLAN SAYS THERE ARE` : `the plan says there are ${fmtAlt(have)} ft`;
    return `landing at ${hundred(L.weight_lb)} lb: touchdown ${hundred(L.touchdown_ft)} ft past the aiming point, rollout to ${hundred(L.slow_ft)} ft past it; runway to have past the aiming point ${hundred(L.runway_ft)} ft (${verdict})`;
  }

  /* ------------------------------------------------------------- the plan editor */
  const enrouteNow = () => !!(link.status && link.status.started && (link.status.kind === 'route' || link.status.kind === 'hold'));
  /** The forecast of the plan being edited (or held): legs, result, and where it starts. */
  function planForecast(plan, which) {
    const elev = plan.field.elev_ft;
    const flying = enrouteNow();
    if (which === 'lost') {
      const first = plan.lost_link[0].points[0];
      const st = stateNow(elev);
      const legs = G.plancheck.legs(plan.lost_link, null, plan.field);
      return { legs, r: forecast.predict(legs, { alt_ft: first[2], weight_lb: st.weight_lb, fuel_lb: st.fuel_lb }), from: 'its first point, with the fuel there is now' };
    }
    const items = flying ? plan.items.slice(plan.items.findIndex((it) => it.kind === 'route')) : plan.items;
    const legs = G.plancheck.legs(items, flying ? here() : null, plan.field);
    return { legs, r: forecast.predict(legs, stateNow(elev)), from: flying ? 'where the aircraft is now' : 'the takeoff' };
  }

  /* ------------------------------------------------------------- the route planner (in the plan editor) */
  const RP_KEY = 'gcs.route';
  let rp = null; // the last search: { routes, notes, errors, pick }
  try {
    const saved = JSON.parse(localStorage.getItem(RP_KEY) || 'null');
    if (saved) {
      if (['prefer', 'require', 'off'].includes(saved.sites)) $('rp-sites').value = saved.sites;
      $('rp-short').checked = !!saved.short;
      if (saved.alt) $('rp-alt').value = saved.alt;
      $('rp-wind').checked = saved.wind !== false;
    }
  } catch (e) { /* no storage: the defaults */ }
  const rpSave = () => {
    try {
      localStorage.setItem(RP_KEY, JSON.stringify({ sites: $('rp-sites').value, short: $('rp-short').checked, alt: $('rp-alt').value, wind: $('rp-wind').checked }));
    } catch (e) { /* kept until the page closes */ }
  };
  ['rp-sites', 'rp-short', 'rp-alt', 'rp-wind'].forEach((id) => $(id).addEventListener('change', rpSave));

  function rpClear() {
    rp = null;
    map.data.routeView = null;
    $('rp-cards').innerHTML = '';
    $('rp-use').disabled = true;
  }

  function rpShow() {
    if (!rp || !rp.routes[rp.pick]) {
      map.data.routeView = null;
      return;
    }
    const c = rp.routes[rp.pick];
    map.data.routeView = { points: [rp.start].concat(c.points), gaps: c.coverage ? c.coverage.gaps : [] };
    document.querySelectorAll('.rcard').forEach((el, i) => el.classList.toggle('sel', i === rp.pick));
    $('rp-use').disabled = false;
    map.draw();
  }

  function rpCards() {
    $('rp-cards').innerHTML = rp.routes.map((c, i) => {
      const w = G.routeinputs.words(c);
      return `<label class="rcard ${c.direct ? 'direct' : ''}" data-i="${i}"><input type="radio" name="rp-pick" ${i === rp.pick ? 'checked' : ''}><b>${esc(w.title)}</b> <span class="stats">${esc(w.stats)}</span>${w.diff ? `<div class="line2">${esc(w.diff)}</div>` : ''}${w.reach ? `<div class="line2 ${/^no /.test(w.reach) ? 'nosite' : ''}">${esc(w.reach)}</div>` : ''}${w.avoids ? `<div class="line2">${esc(w.avoids)}</div>` : ''}${w.warnings.map((t) => `<div class="warn">${esc(t)}</div>`).join('')}</label>`;
    }).join('');
  }

  $('rp-cards').addEventListener('change', (e) => {
    const card = e.target.closest('.rcard');
    if (card && rp) {
      rp.pick = Number(card.getAttribute('data-i'));
      rpShow();
    }
  });

  async function findRoutes() {
    if (!editor || editor.which !== 'route') return;
    const plan = editor.plan;
    const goal = G.routeinputs.goalOf(plan);
    const status = (t) => ($('rp-status').textContent = t);
    if (!goal) return status('The plan has no landing to route to.');
    const flying = enrouteNow();
    const st = G.routeinputs.startOf(plan, flying, here(), tel.alt);
    const state = stateNow(plan.field.elev_ft);
    const useWind = $('rp-wind').checked;
    const siteMode = $('rp-sites').value;
    const altitudes = $('rp-alt').value === 'best' ? undefined : [Number($('rp-alt').value)];
    $('rp-go').disabled = true;
    rpClear();
    status('Fetching the winds and the airports…');
    const notes = [];
    try {
      const span = Math.max(Math.abs(goal.fix[0] - st.pos[0]), Math.abs(goal.fix[1] - st.pos[1]) * Math.cos((st.pos[0] * Math.PI) / 180));
      const m = Math.max(1.5, 0.35 * span) + 0.5;
      const c = Math.cos((((st.pos[0] + goal.fix[0]) / 2) * Math.PI) / 180);
      const box = [Math.max(-85, Math.min(st.pos[0], goal.fix[0]) - m), Math.min(st.pos[1], goal.fix[1]) - m / c, Math.min(85, Math.max(st.pos[0], goal.fix[0]) + m), Math.max(st.pos[1], goal.fix[1]) + m / c];
      if (!ov.prefs.offline && !demo) {
        if (siteMode !== 'off') await ov.airports.ensure([(st.pos[0] + goal.fix[0]) / 2, (st.pos[1] + goal.fix[1]) / 2], Math.max(500, (span * 60) / 2 + 250));
        if (useWind && ov.wind.prefetch) {
          const levels = [...new Set((altitudes || G.router.ALTITUDES).map((a) => G.weather.levelFor(a)))];
          const r = await ov.wind.prefetch(box, levels);
          if (!r.ok) notes.push('The winds could not be had (' + r.status + '): the route is planned in still air.');
        }
      } else if (ov.prefs.offline && useWind && !demo) notes.push('The page is offline: no winds, and only the airports that were kept in this browser.');
      const windOk = useWind && (demo || ov.wind.cells.size > 0);
      if (useWind && !windOk && !notes.length) notes.push('No winds are loaded: the route is planned in still air.');
      const siteInfo = G.routeinputs.sites(plan, ov.airports.list, forecast, state.weight_lb);
      if (siteMode !== 'off') notes.push('Landing sites: ' + siteInfo.note + '.');
      const out = await G.router.alternativesAsync({
        start: st.pos, start_alt_ft: st.alt_ft, goal: goal.fix, fix_alt_ft: goal.fix_alt_ft, weight_lb: state.weight_lb, fuel_lb: state.fuel_lb, fc: forecast, perf: G.perfdata,
        wind: windOk ? (la, lo, alt, h) => ov.wind.at(la, lo, alt, h) : null, hours: ov.prefs.windHours, zones: ov.zones(), hazards: ov.hazardList(), now: Date.now(), altitudes,
        legsFor: (pts) => G.plancheck.legs([{ kind: 'route', points: pts }, goal.land], st.pos, plan.field),
        sites: siteInfo.list, glide: (a, e) => G.reach.radius(a, e) / geo.NM, siteMode, shortStrips: $('rp-short').checked,
      }, (name) => status(`Working out the ${name.toLowerCase()} route…`));
      if (!out.ok) {
        status('No route: ' + out.error);
        $('rp-go').disabled = false;
        return;
      }
      rp = { routes: out.routes, pick: 0, start: st.pos };
      out.notes.forEach((n) => notes.push(n));
      out.errors.forEach((n) => notes.push(n));
      if (!demo && !ov.hazards.awc) notes.push('Weather hazards (SIGMET) need the helper: none were avoided.');
      status(notes.join(' '));
      rpCards();
      rpShow();
    } catch (e) {
      status('The route planner failed: ' + e.message);
    }
    $('rp-go').disabled = false;
  }
  $('rp-go').addEventListener('click', findRoutes);
  $('rp-use').addEventListener('click', () => {
    if (!editor || !rp) return;
    const c = rp.routes[rp.pick];
    if (editor.setRoute(c.points)) {
      $('rp-undo').disabled = false;
      $('rp-status').textContent = `The route is in the plan (${c.names.join(' · ')}). Nothing is sent: Send plan… does that, and the aircraft checks it.`;
      map.data.routeView = null;
      renderEditor();
    }
  });
  $('rp-undo').addEventListener('click', () => {
    if (editor && editor.undoRoute()) {
      $('rp-undo').disabled = true;
      $('rp-status').textContent = 'The route is as it was.';
      renderEditor();
    }
  });

  function renderEditor() {
    const box = $('editor');
    box.hidden = !editor;
    $('c-edit').classList.toggle('on', !!editor);
    if (!editor) {
      if (rp) rpClear();
      $('rp-undo').disabled = true;
      map.data.handles = null;
      map.data.editing = null;
      drawProfile();
      map.draw();
      return;
    }
    const plan = editor.plan;
    $('ed-name').textContent = `"${plan.id}"`;
    $('ed-route').classList.toggle('on', editor.which === 'route');
    $('ed-lost').classList.toggle('on', editor.which === 'lost');
    const bad = G.plancheck.checkPlan(plan);
    let rowsHtml = '<tr><th>#</th><th>height ft</th><th>leg nmi</th><th>time</th><th>fuel lb</th><th></th></tr>';
    let warn = bad ? [`<span class="bad">The aircraft will refuse this: ${esc(bad)}</span>`] : [];
    let fc = null;
    if (!bad && editor.item()) {
      fc = planForecast(plan, editor.which);
      const item = editor.item();
      fc.legs.forEach((leg, n) => {
        const pt = fc.r.points[n];
        const mine = leg.item === item && leg.index !== undefined;
        const name = leg.kind === 'takeoff' ? 'takeoff' : leg.label || (mine ? String(leg.index + 1) : '·');
        const cls = mine ? (leg.index === editor.selected ? 'sel' : '') : 'fixed';
        const altCell = mine ? `<input type="number" step="500" min="0" max="65000" value="${leg.alt_ft}" data-alt="${leg.index}">` : fmtAlt(leg.alt_ft);
        rowsHtml += `<tr class="${cls}" data-row="${mine ? leg.index : ''}"><td>${name}</td><td>${altCell}${pt.reached ? '' : ' <span class="bad" title="not reached by then">!</span>'}</td><td>${(leg.dist_ft / geo.NM).toFixed(1)}</td><td>${hms(pt.t_s)}</td><td>${fmtAlt(pt.fuel_lb)}</td><td>${mine ? `<button data-del="${leg.index}" title="delete this point">×</button>` : ''}</td></tr>`;
      });
      warn = warn.concat(fc.r.warnings.map(esc));
      const roll = landingWords(fc.r, plan.field);
      if (roll) warn.push(`<span class="small">${esc(roll[0].toUpperCase() + roll.slice(1))}.</span>`);
      warn.push(`<span class="small">Forecast from ${fc.from}: ${hms(fc.r.total.t_s)}, ${fmtAlt(fc.r.total.fuel_used_lb)} lb of fuel, ${(fc.r.total.dist_ft / geo.NM).toFixed(0)} nmi. No wind.</span>`);
      if (editor.which === 'route' && (demo || ov.wind.cells.size > 0)) {
        // the same legs with the wind aloft the planner fetched: the aircraft does not use it, and neither does the forecast above
        const wf = forecast.predict(fc.legs, stateNow(plan.field.elev_ft), { wind: (la, lo, alt, h) => ov.wind.at(la, lo, alt, h), hours: ov.prefs.windHours });
        warn.push(`<span class="small">With the winds aloft (${demo ? 'made up' : 'Open-Meteo'}, ${ov.prefs.windHours ? '+' + ov.prefs.windHours + ' h' : 'now'}): ${hms(wf.total.t_s)}, ${fmtAlt(wf.total.fuel_used_lb)} lb of fuel.</span>`);
      }
    }
    if ($('ed-table').dataset.html !== rowsHtml && !$('ed-table').contains(document.activeElement)) {
      $('ed-table').innerHTML = rowsHtml;
      $('ed-table').dataset.html = rowsHtml;
    }
    $('rp').hidden = editor.which !== 'route';
    $('rp-undo').disabled = !editor.undo;
    warn = warn.concat(ov.editNotes(plan, editor.which, tel.gs).map((t) => `<span class="small">${esc(t)}</span>`));
    $('ed-warn').innerHTML = warn.join('<br>');
    if (document.activeElement !== $('ed-runway')) $('ed-runway').value = plan.field.runway_past_aim_ft > 0 ? plan.field.runway_past_aim_ft : '';
    $('ed-send').disabled = !!bad || !(link.state.mode === 'live');
    map.data.handles = editor.points().map((p) => [p[0], p[1]]);
    map.data.selected = editor.selected;
    map.data.editing = { plan, fc };
    map.data.preview = armed && armed.preview ? armed.preview() : { plan: { items: editor.which === 'lost' ? plan.lost_link : plan.items, field: plan.field } };
    drawProfile();
    map.draw();
  }

  $('ed-table').addEventListener('change', (e) => {
    const i = e.target.getAttribute('data-alt');
    if (i !== null && editor) {
      editor.setAlt(Number(i), Number(e.target.value));
      e.target.blur();
      renderEditor();
    }
  });
  $('ed-table').addEventListener('click', (e) => {
    if (!editor) return;
    const del = e.target.getAttribute('data-del');
    const row = e.target.closest('tr');
    if (del !== null) editor.remove(Number(del));
    else if (row && row.getAttribute('data-row') !== '' && row.getAttribute('data-row') !== null && e.target.tagName !== 'INPUT') editor.selected = Number(row.getAttribute('data-row'));
    else return;
    renderEditor();
  });
  $('c-edit').addEventListener('click', () => {
    if (editor) editor = null;
    else if (link.plan) editor = new G.PlanEditor(link.plan);
    else {
      $('conn').textContent = 'There is no plan to edit yet: send the demo plan or a plan file first, or load one and edit it before sending.';
      return;
    }
    arm(null);
    renderEditor();
    if (editor) $('editor').scrollIntoView({ block: 'nearest' });
  });
  $('ed-route').addEventListener('click', () => {
    editor.edit('route');
    renderEditor();
  });
  $('ed-lost').addEventListener('click', () => {
    editor.edit('lost');
    renderEditor();
  });
  // how much runway there is past the aiming point: the station's own note in the plan, for the landing's forecast
  $('ed-runway').addEventListener('change', (e) => {
    if (!editor) return;
    const v = Number(e.target.value);
    if (v > 0) editor.plan.field.runway_past_aim_ft = Math.round(v);
    else delete editor.plan.field.runway_past_aim_ft;
    renderEditor();
  });
  $('ed-close').addEventListener('click', () => {
    editor = null;
    arm(null);
    renderEditor();
  });
  $('ed-save').addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(editor.plan, null, 1)], { type: 'application/json' }));
    a.download = editor.plan.id.replace(/[^a-z0-9-]+/gi, '-').replace(/^-|-$/g, '') + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $('ed-send').addEventListener('click', () => {
    const flying = enrouteNow();
    const p = editor.toSend(flying);
    arm({
      name: 'plan', button: $('ed-send'), ready: () => true, args: () => p, preview: () => ({ plan: p }),
      text: () => `${planSummary(p)}${flying ? '. The aircraft leaves what it is flying for this route at once' : ''}`,
      sent: () => {
        editor = null;
        renderEditor();
      },
    });
  });

  /* ------------------------------------------------------------- the height profile under the map */
  function drawProfile() {
    const c = $('profile');
    const r = c.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== Math.round(r.width * dpr)) {
      c.width = Math.round(r.width * dpr);
      c.height = Math.round(r.height * dpr);
    }
    const x = c.getContext('2d');
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = r.width;
    const h = r.height;
    x.clearRect(0, 0, w, h);
    let plan = null;
    let fc = null;
    let colour = '#c9d1d9';
    if (map.data.editing) {
      plan = map.data.editing.plan;
      fc = map.data.editing.fc;
      colour = G.COL.preview;
    } else if (link.plan && G.plancheck.checkPlan(link.plan) === null) {
      plan = link.plan;
      fc = planForecast(plan, 'route');
    }
    x.font = '11px ui-sans-serif, system-ui, sans-serif';
    x.fillStyle = '#8795a3';
    if (!fc) {
      x.fillText('height along the plan: no plan', 10, 16);
      return;
    }
    const total = Math.max(fc.r.total.dist_ft, 1);
    const top = Math.max(10000, ...fc.r.profile.map((p) => p[1])) * 1.12;
    const px = (d) => 44 + (d / total) * (w - 60);
    const py = (a) => h - 18 - (a / top) * (h - 30);
    x.strokeStyle = '#1c2530';
    x.lineWidth = 1;
    for (let a = 0; a <= top; a += top > 30000 ? 20000 : 10000) {
      x.beginPath();
      x.moveTo(44, py(a));
      x.lineTo(w - 16, py(a));
      x.stroke();
      x.fillText(`${a / 1000}k`, 10, py(a) + 4);
    }
    x.fillText(`height along ${map.data.editing ? 'the plan being edited' : 'the plan'}, from ${fc.from}: ${(total / geo.NM).toFixed(0)} nmi, ${hms(fc.r.total.t_s)}`, 50, 12);
    // the heights asked for, and the height forecast
    x.strokeStyle = G.COL.active;
    x.setLineDash([3, 4]);
    x.beginPath();
    let d0 = 0;
    fc.legs.forEach((leg, n) => {
      const d1 = fc.r.points[n].dist_ft;
      if (leg.kind !== 'takeoff' && leg.kind !== 'land') {
        x.moveTo(px(d0), py(leg.alt_ft));
        x.lineTo(px(d1), py(leg.alt_ft));
      }
      d0 = d1;
    });
    x.stroke();
    x.setLineDash([]);
    x.strokeStyle = colour;
    x.lineWidth = 2;
    x.beginPath();
    fc.r.profile.forEach((p, i) => (i ? x.lineTo(px(p[0]), py(p[1])) : x.moveTo(px(p[0]), py(p[1]))));
    x.stroke();
    fc.r.points.forEach((p, n) => {
      const leg = fc.legs[n];
      if (leg.kind === 'takeoff') return;
      x.fillStyle = p.reached ? colour : '#ff5252';
      x.fillRect(px(p.dist_ft) - 3, py(p.alt_ft) - 3, 6, 6);
      x.fillStyle = '#8795a3';
      x.fillText(leg.label || (leg.index !== undefined ? String(leg.index + 1) : ''), px(p.dist_ft) - 3, h - 5);
    });
  }
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

  /* ------------------------------------------------------------- the link, this station, messages, the map's orientation */
  const restored = new G.linkinfo.Restored();
  const DELAYS = [[0, 'none (line of sight)'], [600, '0.6 s'], [1200, '1.2 s (satellite)'], [2400, '2.4 s']];
  const delaySel = $('st-delay');
  if (!DELAYS.some((d) => d[0] === link.latency)) DELAYS.push([link.latency, `${link.latency} ms (the address's)`]);
  delaySel.innerHTML = DELAYS.map((d) => `<option value="${d[0]}">${d[1]}</option>`).join('');
  delaySel.value = String(link.latency);
  delaySel.addEventListener('change', () => (link.latency = Number(delaySel.value))); // from the next message on

  function renderStation(live) {
    $('st-name').textContent = link.station;
    const where = String(link.state.message || '').replace(/^ws:\/\//, '').replace(/\/PropertyListener$/, '');
    $('st-conn').textContent = demo ? 'in this page (demo)' : `${link.state.mode}${where ? ': ' + where : ''}`;
    $('st-heard').textContent = link.lastDown === null ? 'never' : `${((Date.now() - link.lastDown) / 1000).toFixed(1)} s ago`;
    const a = link.answerMs();
    $('st-answer').textContent = a === null ? 'no command answered yet' : a < 1000 ? `${Math.round(a)} ms` : `${(a / 1000).toFixed(1)} s`;
    $('st-input').textContent = inputNow;
  }

  // messages to the other stations: not through the aircraft, not delayed
  let unread = 0;
  $('messages-box').hidden = demo; // the demo has one station
  link.on((what, m) => {
    if (what === 'message' && !m.mine) {
      unread += 1;
      beep('message');
    }
  });
  const sendMessage = () => {
    if (link.say($('msg-text').value)) $('msg-text').value = '';
  };
  $('msg-send').addEventListener('click', sendMessage);
  $('msg-text').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });
  const seen = () => (unread = 0);
  $('msg-text').addEventListener('focus', seen);
  $('msg-log').addEventListener('pointerdown', seen);
  function renderMessages(live) {
    if (demo) return;
    $('msg-send').disabled = $('msg-text').disabled = !live;
    const fresh = unread;
    const html = link.messages.slice(-8).map((m, i, a) => `<li class="${m.mine ? 'mine' : ''}${!m.mine && i >= a.length - fresh ? ' new' : ''}"><span class="when">${clock(m.at)}</span><span><b>${esc(m.station)}</b> ${esc(m.text)}</span></li>`).join('');
    if ($('msg-log').dataset.html !== html) {
      $('msg-log').innerHTML = html;
      $('msg-log').dataset.html = html;
      $('msg-log').scrollTop = $('msg-log').scrollHeight;
    }
    $('messages-box').querySelector('h2').textContent = fresh ? `Messages (${fresh} new)` : 'Messages';
  }

  let trackUp = false;
  function mapUp() {
    const deg = Number.isFinite(tel.trackRad) && (tel.gs || 0) > 20 ? (tel.trackRad * 180) / Math.PI : tel.hdg;
    map.up = trackUp && Number.isFinite(deg) ? ((deg % 360) + 360) % 360 : 0;
  }
  $('orient').addEventListener('click', () => {
    trackUp = !trackUp;
    $('orient').textContent = trackUp ? 'track up' : 'north up';
    $('orient').classList.toggle('on', trackUp);
    mapUp();
    map.draw();
  });

  // closing the page cuts the link of the station in control of a flight: ask first
  window.addEventListener('beforeunload', (e) => {
    const w = G.linkinfo.closingWarning(link.status, link.station);
    if (!w) return undefined;
    e.preventDefault();
    e.returnValue = w;
    return w;
  });

  /* ------------------------------------------------------------- showing */
  function render() {
    mapUp();
    const s = link.status;
    const live = link.state.mode === 'live' && link.lastDown !== null && Date.now() - link.lastDown < 3000 + link.latency;
    // only the station that has control commands (before anyone has it, the first to speak gets it)
    const mine = renderControl(s, live) || !!(live && s && s.control && !s.control.holder);
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
    const count = live ? G.linkinfo.countdown(s) : null; // the aircraft has stopped hearing the station in control: how long, and how long is left
    $('link-note').classList.toggle('count', !!count);
    $('link-note').textContent = count
      ? G.linkinfo.countdownText(count, link.station)
      : live
        ? `${link.latency ? link.latency / 1000 + ' s delay · ' : ''}if lost: route home after ${timeout} s`
        : s && s.started ? `the aircraft goes home by itself ${timeout} s after the last contact` : '';
    const comeBack = restored.update(sending, Date.now());
    renderStation(live);
    renderMessages(live);
    $('n-hdg').textContent = Number.isFinite(tel.hdg) ? String(Math.round(tel.hdg) % 360).padStart(3, '0') + '°' : '-';
    $('n-mach').textContent = Number.isFinite(tel.mach) ? tel.mach.toFixed(3) : '-';
    $('n-gs').textContent = Number.isFinite(tel.gs) ? Math.round(tel.gs) + ' kt' : '-';
    $('n-vs').textContent = Number.isFinite(tel.vs) ? (tel.vs * 60 >= 0 ? '+' : '') + Math.round(tel.vs * 6) * 10 : '-';
    $('n-fuel').textContent = Number.isFinite(tel.fuel) ? fmtAlt(tel.fuel) : '-';
    $('n-thr').textContent = Number.isFinite(tel.thr) ? Math.round(tel.thr * 100) + ' %' : '-';
    // one list: the aircraft's alerts and the station's own, ranked, each with what to do
    // other aircraft against our own path; the station raises the traffic alert (the aircraft has no sensor for it)
    const ownPath = Number.isFinite(tel.lat) && Number.isFinite(tel.trackRad) ? { lat: tel.lat, lon: tel.lon, alt_ft: tel.alt, track: (tel.trackRad * 180) / Math.PI, kt: tel.gs || 0, vs_fps: tel.vs || 0 } : null;
    const airborneNow = !!(s && s.started && !['taxi', 'takeoff', 'done'].includes(s.kind));
    trafficList.forEach((t) => (t.threat = ownPath ? G.traffic.threat(ownPath, t) : null));
    const trafficAlert = airborneNow ? G.traffic.alert(trafficList) : null;
    map.data.traffic = trafficList;
    // the layers: the situation, which are shown and why; their advisories join the one alert list
    const ownPos = Number.isFinite(tel.lat) && Number.isFinite(tel.lon) ? { lat: tel.lat, lon: tel.lon, alt_ft: tel.alt, agl_ft: tel.agl, track: Number.isFinite(tel.trackRad) ? (tel.trackRad * 180) / Math.PI : tel.hdg, gs_kt: tel.gs || 0, vs_fps: tel.vs || 0 } : null;
    const ctx = ov.situation.update({
      now: Date.now(), own: ownPos, status: live ? s : null, plan: link.plan, editing: !!editor, station, latency, traffic: trafficList, alertIds: alerts.items.map((a) => a.id),
      cameraLocked: live && !!G.camera.state(link.values).target, areas: ov.areas.length, hours: ov.prefs.windHours, engineOut: tel.failed > 0.5,
    });
    layers.update(ctx);
    if (Number.isFinite(tel.weight)) ov.weightNow = tel.weight;
    if (Number.isFinite(tel.fuel)) ov.fuelNow = tel.fuel;
    ov.tick(ctx);
    const legend = ov.legendHtml() + (map.data.routeView ? `<span class="k2" style="border-top:3px dashed ${G.COL.preview}">route on its card</span>${map.data.routeView.gaps && map.data.routeView.gaps.length ? `<span class="k2" style="border-top:5px solid ${G.COL.lost}">no landing site in reach</span>` : ''}` : '');
    if ($('legend2').dataset.html !== legend) {
      $('legend2').innerHTML = legend;
      $('legend2').dataset.html = legend;
    }
    const own = (trafficAlert ? [trafficAlert] : []).concat(ov.alerts(ctx));
    if (comeBack) own.push({ id: 'link-restored', level: 'advisory', text: 'LINK RESTORED', action: s && s.link_lost ? 'The aircraft is still on its lost-link route: Resume plan to go on with the mission' : '' });
    const list = alerts.update(s ? s.alerts : [], link.lastDown, !!(s && s.started) || link.lastDown !== null, own);
    const html = list.map((a) => `<div class="alert ${a.level} ${a.acked ? 'acked' : 'new'}"><b>${esc(a.text)}</b><span class="do">${esc(a.action)}</span>${a.acked ? '' : `<button data-ack="${esc(a.id)}">OK</button>`}</div>`).join('');
    if ($('alerts').dataset.html !== html) {
      $('alerts').innerHTML = html;
      $('alerts').dataset.html = html;
    }
    const tone = alerts.tone();
    if (tone && Date.now() - toneAt > (tone === 'warning' ? 2000 : tone === 'link' ? 4000 : 5000)) {
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
      b.disabled = !mine;
    });
    $('nav-note').textContent = tel.miscompare > 0.5 ? '· two disagree' : '';
    // which commands make sense now
    const enroute = !!(live && s && s.started && (s.kind === 'route' || s.kind === 'hold'));
    const byHand = !!(s && s.manual > 0);
    $('c-start').disabled = !(mine && s && s.plan && !s.started);
    $('c-demo').disabled = !mine;
    $('c-goto').disabled = $('c-hold').disabled = $('c-alt').disabled = !(mine && enroute && !byHand);
    $('c-resume').disabled = !(mine && s && s.off_plan && s.contingency !== 'engine' && s.kind !== 'done' && !byHand);
    $('c-home').disabled = !(mine && enroute && link.plan && link.plan.lost_link && !byHand);
    $('c-timeout').disabled = !(mine && s);
    $('m-auto').disabled = !(mine && byHand);
    $('m-prot').disabled = !(mine && enroute && s.manual !== 1) || demo; // flying by hand needs the flight model
    $('m-direct').disabled = !(mine && enroute && s.manual !== 2) || demo;
    $('m-auto').classList.toggle('on', !!s && s.manual === 0);
    $('m-prot').classList.toggle('on', !!s && s.manual === 1);
    $('m-direct').classList.toggle('on', !!s && s.manual === 2);
    $('follow').classList.toggle('on', map.follow);
    // sent commands and the aircraft's notes
    $('log').innerHTML = link.commands.slice(-8).reverse().map((c) => {
      const label = { sent: 'sent…', accepted: 'accepted', rejected: 'REJECTED', 'no answer': 'NO ANSWER' }[c.state];
      return `<li><span class="when">${clock(c.sentAt)}</span><span>${esc(c.name)}${c.reason ? `<div class="why">${esc(c.reason)}</div>` : ''}</span><span class="st ${c.state.split(' ')[0]}">${label}</span></li>`;
    }).join('');
    $('events').innerHTML = (s ? s.events.slice().reverse() : []).map((e) => `<li><span class="when">${mmss(e[0])}</span><span>${esc(e[1])}</span></li>`).join('');
    $('conn').textContent = $('conn').textContent.startsWith('The demo') || $('conn').textContent.startsWith('That file') ? $('conn').textContent : `${link.state.message || ''}`;
    // glide reach, by the aircraft's own planner's rules: shown whenever it is flying
    const sitesNow = link.plan && link.plan.sites ? link.plan.sites : [];
    map.data.reach = enroute && here() && sitesNow.length && Number.isFinite(tel.trackRad)
      ? { radiusFt: G.reach.radius(tel.alt, link.plan.field.elev_ft), sites: sitesNow.map((st) => {
          const m = G.reach.margin(st, here(), tel.alt, (tel.trackRad * 180) / Math.PI);
          return { aim: st.aim, inReach: m >= 0, inHand: m + G.reach.IN_HAND }; // the planner keeps 1,000 ft of it back when choosing
        }) }
      : null;
    $('c-edit').disabled = !live;
    if (editor) $('ed-send').disabled = $('ed-send').disabled || !mine;
    if (editor) renderEditor();
    else drawProfile();
    map.data.plan = link.plan;
    map.data.status = live ? s : null;
    map.data.airborne = enroute;
    map.data.lostLabel = `if the link is lost: after ${timeout} s`;
    const cam = G.camera.state(link.values);
    map.data.camera = live ? cam.target : null;
    $('cam-state').textContent = demo ? 'the stand-in aircraft of the demo has no camera' : !live ? '' : cam.text + (cam.level ? '; horizon kept level' : '');
    $('cam-level').classList.toggle('on', cam.level);
    document.querySelectorAll('#camera button').forEach((b) => (b.disabled = demo || !live));
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
  window.addEventListener('resize', () => {
    map.resize();
    drawProfile();
  });
  map.resize();
  link.start(Object.values(TELEMETRY).concat(Object.values(G.camera.PATHS)));
  setInterval(() => {
    if (armed) renderConfirm();
    render();
  }, 250);
  window.GCSApp = { link, map, tel, pfd, alerts, layers, ov, get editor() { return editor; }, forecastTo, planForecast, stateNow, forecast }; // for looking at from the console
})();
