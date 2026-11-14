/**
 * Made-up airspace, fields and weather for the demo (?demo=1, or ?overlays=demo against the simulator server), so that the layers
 * can be tried with no network and no files. Every name is invented; none of it is a real zone, field or report, and it sits around
 * the demo's made-up field (js/demoplan.js).
 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const A = node ? require('./airspace.js') : root.GCS.airspace;
  const geo = node ? require('./geo.js') : root.GCS.geo;
  const NM = geo.NM;
  const FIELD = [34.9, -117.88];
  const circle = (lat, lon, nm) => ({ lat, lon, r_ft: nm * NM });
  const box = (lat, lon, dLat, dLon) => [[lat + dLat, lon - dLon], [lat + dLat, lon + dLon], [lat - dLat, lon + dLon], [lat - dLat, lon - dLon]];

  const zones = () => [
    A.make({ name: 'R-9001 DEMO RESTRICTED', kind: 'restricted', lower: { ft: 15000, ref: 'FL' }, upper: { ft: 40000, ref: 'FL' }, circle: circle(35.085, -117.36, 4), src: 'demo (made up)', times: 'BY NOTAM (made up)' }),
    A.make({ name: 'DEMO NORTH MOA', kind: 'moa', lower: { ft: 5000, ref: 'AGL' }, upper: { ft: 17999, ref: 'MSL' }, rings: [box(35.4, -117.6, 0.18, 0.3)], src: 'demo (made up)' }),
    A.make({ name: 'DEMO FIELD CLASS D', kind: 'classD', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 4800, ref: 'MSL' }, circle: circle(FIELD[0], FIELD[1], 4.5), src: 'demo (made up)' }),
    A.make({ name: 'W-9002 DEMO WARNING AREA', kind: 'warning', lower: { ft: 0, ref: 'AGL' }, upper: { ft: 99999, ref: 'MSL' }, rings: [box(34.45, -117.5, 0.15, 0.25)], src: 'demo (made up)' }),
  ];

  /** Invented fields (idents begin with X), with runways: [{ le, he, len_ft, hdg }]. */
  const airports = () => [
    { ident: 'XDM1', name: 'Demo Field', lat: 34.9, lon: -117.88, elev_ft: 2300, type: 'medium_airport', country: '', city: '', rwys: [{ le: '04', he: '22', len_ft: 12000, width_ft: 200, surface: 'CON', paved: true, hdg: 40 }], rwy_ft: 12000, paved_ft: 12000 },
    { ident: 'XDM2', name: 'Demo East', lat: 35.12, lon: -116.95, elev_ft: 3100, type: 'medium_airport', country: '', city: '', rwys: [{ le: '09', he: '27', len_ft: 8000, width_ft: 150, surface: 'ASP', paved: true, hdg: 90 }], rwy_ft: 8000, paved_ft: 8000 },
    { ident: 'XDM3', name: 'Demo South', lat: 34.35, lon: -117.9, elev_ft: 2500, type: 'small_airport', country: '', city: '', rwys: [{ le: '16', he: '34', len_ft: 6200, width_ft: 100, surface: 'ASP', paved: true, hdg: 160 }], rwy_ft: 6200, paved_ft: 6200 },
    { ident: 'XDM4', name: 'Demo Strip', lat: 35.3, lon: -118.4, elev_ft: 1800, type: 'small_airport', country: '', city: '', rwys: [{ le: '07', he: '25', len_ft: 3600, width_ft: 60, surface: 'GRVL', paved: false, hdg: 70 }], rwy_ft: 3600, paved_ft: 0 },
  ];

  /** One made-up turbulence area, FL250 to FL350, across the demo plan's last leg's side. */
  const hazards = (now) => [{ source: 'SIGMET', id: 'SIGMET DEMO 1', hazard: 'TURB', kind: 'turb', severity: 5, lo_ft: 25000, hi_ft: 35000, from: now - 3600000, to: now + 7200000, rings: [box(34.7, -117.8, 0.25, 0.3)], text: 'made up for the demo' }];

  /** A wind field with the interface of weather.WindField: 45 kt from 250 degrees, a little stronger to the north. */
  class DemoWind {
    constructor() {
      this.step = 0.5;
      this.status = 'made-up wind for the demo';
      this.cells = new Map(); // none: the wind is a formula (the real field's cache is read by the page)
    }

    async ensure() {}

    at(lat) {
      return { spd: 45 + (lat - 35) * 10, dir: 250, level: 70 };
    }

    arrows(boxDeg) {
      const out = [];
      for (const c of lattice(boxDeg, this.step)) out.push({ lat: c.lat, lon: c.lon, spd: this.at(c.lat).spd, dir: 250 });
      return out;
    }
  }

  function lattice(b, step) {
    const out = [];
    for (let i = Math.floor(b[0] / step); i <= Math.ceil(b[2] / step); i++) for (let j = Math.floor(b[1] / step); j <= Math.ceil(b[3] / step); j++) out.push({ lat: i * step, lon: j * step });
    return out;
  }

  /** A made-up report for the demo field: wind from 330 at 16 kt (a crosswind on runway 04), scattered cloud, good visibility. */
  const metar = (now) => ({ id: 'XDM1', wdir: 330, wspd: 16, wgst: 22, vis_sm: 10, ceiling_ft: null, cat: 'VFR', raw: 'XDM1 made up for the demo 33016G22KT 10SM SCT120', time: now, src: 'demo (made up)' });

  const api = { zones, airports, hazards, DemoWind, metar, FIELD };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).demodata = api;
})(typeof window !== 'undefined' ? window : globalThis);
