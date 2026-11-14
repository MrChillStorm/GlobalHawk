/*
 * The belly camera, for the sensor operator: what it is locked on, in words and for the map, and the commands the
 * aircraft's camera takes (Nasal/camera.nas, /sim/globalhawk/camera/command). They are not flight commands: they go
 * to the camera, not through the aircraft's command link, and any station may send them, with or without control.
 */
(function (root) {
  'use strict';
  const CAM = '/sim/globalhawk/camera/';
  const PATHS = { lock: CAM + 'lock', name: CAM + 'name', lat: CAM + 'target-lat', lon: CAM + 'target-lon', range: CAM + 'range-nm', level: CAM + 'level' };

  const deg = (v, pos, neg) => `${Math.abs(v).toFixed(4)} ${v >= 0 ? pos : neg}`;

  /** From the camera's properties (as they come down: strings or numbers): { mode, text, target, level }. */
  function state(values) {
    const mode = String(values[PATHS.lock] || '');
    const lat = Number(values[PATHS.lat]);
    const lon = Number(values[PATHS.lon]);
    const range = Number(values[PATHS.range]);
    const level = values[PATHS.level] === true || Number(values[PATHS.level]) === 1 || values[PATHS.level] === 'true';
    const has = (mode === 'point' || mode === 'object') && Number.isFinite(lat) && Number.isFinite(lon) && values[PATHS.lat] !== '' && values[PATHS.lat] !== undefined;
    if (!has) return { mode: 'free', text: 'free: it looks where it is turned', target: null, level };
    const where = `${deg(lat, 'N', 'S')} ${deg(lon, 'E', 'W')}`;
    const far = Number.isFinite(range) ? `, ${range.toFixed(1)} nmi` : '';
    const what = mode === 'object' ? `locked on ${values[PATHS.name] || 'an object'} at ${where}` : `locked on the point ${where}`;
    return { mode, text: what + far, target: [lat, lon], level };
  }

  /** The command that locks the camera on a point of the map: on the ground there, or, with a height (ft), on that height (an aircraft clicked). */
  function point(p, elevFt) {
    return `point ${p[0].toFixed(6)} ${p[1].toFixed(6)}` + (Number.isFinite(elevFt) ? ` ${Math.round(elevFt)}` : '');
  }

  const api = { CAM, PATHS, state, point };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).camera = api;
})(typeof window !== 'undefined' ? window : globalThis);
