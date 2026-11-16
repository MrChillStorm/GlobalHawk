/**
 * The colours of the map. The station's own seven (plan, flying, lost-link route, preview, sites, trail, camera) keep their
 * meanings; each overlay's main colour is chosen not to be mistaken for any of them or for another overlay's
 * (tests/palette.test.js keeps them at least MIN_DISTANCE apart in RGB). Raster layers (radar, satellite) have their own colour scales.
 */
(function (root) {
  'use strict';
  const MIN_DISTANCE = 90;
  const EXISTING = { plan: '#c9d1d9', active: '#ff4fd8', lost: '#ffb000', preview: '#3fd0ff', site: '#7ee787', trail: '#5b6b7a', camera: '#39ff14' };
  const LAYERS = {
    airspace: '#ff5252',
    airports: '#ffe08a',
    link: '#5a6cff',
    'wx-hazard': '#b5651d',
    wind: '#a528eb',
    terrain: '#5a2828',
    areas: '#00bfa5',
    taxiways: '#aaee22',
    parking: '#cc0088',
  };
  const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const distance = (a, b) => Math.hypot(...rgb(a).map((v, i) => v - rgb(b)[i]));
  const api = { MIN_DISTANCE, EXISTING, LAYERS, distance };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).palette = api;
})(typeof window !== 'undefined' ? window : globalThis);
